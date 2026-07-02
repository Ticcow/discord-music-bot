import asyncio
import io
import logging
import os
import time

import discord

from bot.config import settings
from bot.music import status_panel, yt_dlp_updater
from bot.music.queue import GuildQueue, queues
from bot.music.youtube import FFMPEG_OPTIONS, Track, resolve_stream_url

logger = logging.getLogger(__name__)

_idle_timers: dict[int, asyncio.Task] = {}

# Signatures that show up in ffmpeg's stderr when YouTube rejects a stream
# request outright (bad/expired signature, region lock, removed video, etc).
# A backup net alongside discord.py's own error detection, which can race
# against the ffmpeg process being reaped before it's checked.
_FFMPEG_FAILURE_MARKERS = ("Forbidden", "Error opening input", "Server returned")
_STDERR_LOG_TAIL = 4000


def _playback_likely_failed(error: Exception | None, stderr_text: str) -> bool:
    if error is not None:
        return True
    return any(marker in stderr_text for marker in _FFMPEG_FAILURE_MARKERS)


# A single track failing is normal (region lock, deleted video, a flaky CDN
# blip) - but several failures in a row, across different videos, is the
# actual signature of "YouTube changed something and yt-dlp needs an update"
# rather than anything wrong with one specific track. This counter is
# bot-wide (not per-guild): the same yt-dlp install serves every guild, so a
# streak of failures anywhere is equally good evidence of the same problem.
_CONSECUTIVE_FAILURE_THRESHOLD = 3
_consecutive_playback_failures = 0

# Once triggered, don't check again for an hour - if an update doesn't fix
# it, the problem is something else, and repeatedly restarting the bot to
# retry a pip install that keeps not helping would just add noise/downtime.
_UPDATE_ATTEMPT_COOLDOWN_SECONDS = 60 * 60
_last_update_attempt_at: float | None = None


async def _track_playback_outcome(voice_client: discord.VoiceClient, *, failed: bool) -> None:
    global _consecutive_playback_failures
    if not failed:
        _consecutive_playback_failures = 0
        return

    _consecutive_playback_failures += 1
    if _consecutive_playback_failures >= _CONSECUTIVE_FAILURE_THRESHOLD:
        _consecutive_playback_failures = 0
        await _handle_suspected_yt_dlp_breakage(voice_client)


async def _handle_suspected_yt_dlp_breakage(voice_client: discord.VoiceClient) -> None:
    global _last_update_attempt_at
    now = time.monotonic()
    if _last_update_attempt_at is not None and now - _last_update_attempt_at < _UPDATE_ATTEMPT_COOLDOWN_SECONDS:
        return
    _last_update_attempt_at = now

    channel = status_panel.get_channel(voice_client.guild.id)
    await _send_breakage_notice(
        channel,
        f"{_CONSECUTIVE_FAILURE_THRESHOLD} tracks in a row failed to play - that usually means "
        "YouTube changed something yt-dlp needs to catch up to. Checking for an update...",
    )

    before, after = await yt_dlp_updater.update_yt_dlp()
    if before == after:
        await _send_breakage_notice(
            channel, f"yt-dlp is already up to date ({after or 'unknown'}) - probably not a yt-dlp issue."
        )
        return

    await _send_breakage_notice(channel, f"Updated yt-dlp: {before} -> {after}. Restarting to apply it...")
    logger.info("yt-dlp updated %s -> %s after a suspected-breakage streak, restarting", before, after)
    # Hard exit rather than a graceful shutdown: importing already-loaded
    # modules doesn't pick up an on-disk package upgrade, so the process must
    # actually restart. discord-bot.service has Restart=on-failure and brings
    # it straight back up with the new version.
    os._exit(1)


async def _send_breakage_notice(channel: discord.abc.Messageable | None, message: str) -> None:
    if channel is None:
        return
    try:
        await channel.send(message)
    except discord.HTTPException:
        logger.warning("Failed to post yt-dlp breakage notice")


def cancel_idle_timer(guild_id: int) -> None:
    task = _idle_timers.pop(guild_id, None)
    if task is not None:
        task.cancel()


async def _cleanup_session(guild_id: int, *, reason: str | None = None) -> None:
    cancel_idle_timer(guild_id)
    channel = status_panel.get_channel(guild_id) if reason else None
    queues.get(guild_id).clear()
    await status_panel.clear_panel(guild_id)
    if reason and channel is not None:
        try:
            await channel.send(reason)
        except discord.HTTPException:
            logger.warning("Failed to post disconnect notice for guild %s", guild_id)


async def disconnect_and_cleanup(voice_client: discord.VoiceClient, *, reason: str | None = None) -> None:
    """Tear down a voice session: cancel any idle timer, clear the queue,
    disconnect, and remove the panel. If reason is given, posts a note in
    the panel's channel explaining why the bot left."""
    guild_id = voice_client.guild.id
    await voice_client.disconnect()
    await _cleanup_session(guild_id, reason=reason)


async def cleanup_after_external_disconnect(guild_id: int) -> None:
    """The bot's own voice connection ended without going through disconnect_and_cleanup -
    kicked from the channel, moved somewhere it can't follow, a dropped connection, etc.
    voice_client.disconnect() was never called, so there's nothing to disconnect here,
    just our own bookkeeping (idle timer, queue, panel) left pointing at a dead session."""
    await _cleanup_session(guild_id)


async def _disconnect_after_idle(voice_client: discord.VoiceClient) -> None:
    try:
        await asyncio.sleep(settings.idle_timeout_seconds)
    except asyncio.CancelledError:
        return

    _idle_timers.pop(voice_client.guild.id, None)
    if not voice_client.is_connected():
        return

    await disconnect_and_cleanup(
        voice_client, reason="Left the voice channel after being idle for too long."
    )


def start_idle_timer(voice_client: discord.VoiceClient) -> None:
    """(Re)start the countdown to auto-disconnect. Called whenever nothing is
    actively playing - an empty queue or a paused track."""
    guild_id = voice_client.guild.id
    cancel_idle_timer(guild_id)
    _idle_timers[guild_id] = asyncio.create_task(_disconnect_after_idle(voice_client))


async def ensure_voice_client(interaction: discord.Interaction) -> discord.VoiceClient | None:
    """Return the guild's active voice client, connecting to the invoker's channel if needed.
    Callers must defer the interaction response first."""
    voice_client = interaction.guild.voice_client
    if voice_client is not None:
        return voice_client

    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None:
        await interaction.followup.send("You need to be in a voice channel first.", ephemeral=True)
        return None

    voice_client = await member.voice.channel.connect()
    start_idle_timer(voice_client)
    await status_panel.ensure_panel(interaction.channel, interaction.guild.id)
    return voice_client


def is_authorized(voice_client: discord.VoiceClient | None, member: discord.abc.User) -> bool:
    """True if there's no active session yet (so a new one can be started wherever the
    requester is), or the requester is in the bot's current voice channel."""
    if voice_client is None:
        return True
    return (
        isinstance(member, discord.Member)
        and member.voice is not None
        and member.voice.channel.id == voice_client.channel.id
    )


async def play_next(voice_client: discord.VoiceClient) -> None:
    if not voice_client.is_connected():
        return

    guild_queue: GuildQueue = queues.get(voice_client.guild.id)
    track = guild_queue.pop_next()
    if track is None:
        start_idle_timer(voice_client)
        await status_panel.refresh(voice_client)
        return

    cancel_idle_timer(voice_client.guild.id)

    stream_url, before_options, can_remux_as_opus = await resolve_stream_url(track)
    stderr_buffer = io.BytesIO()
    if can_remux_as_opus:
        # The source is already Opus-encoded - remux it straight through instead of
        # decoding to PCM and having discord.py re-encode it, which is a needless
        # second lossy pass that both degrades quality and costs extra CPU.
        source = discord.FFmpegOpusAudio(
            stream_url,
            before_options=before_options,
            options=FFMPEG_OPTIONS,
            codec="copy",
            stderr=stderr_buffer,
        )
    else:
        source = discord.FFmpegPCMAudio(
            stream_url,
            before_options=before_options,
            options=FFMPEG_OPTIONS,
            stderr=stderr_buffer,
        )

    loop = asyncio.get_running_loop()

    def _after(error: Exception | None) -> None:
        stderr_text = stderr_buffer.getvalue().decode(errors="replace")
        failed = _playback_likely_failed(error, stderr_text)
        if failed:
            logger.error(
                "Playback error for %s: %s\n%s", track.title, error, stderr_text[-_STDERR_LOG_TAIL:]
            )
            asyncio.run_coroutine_threadsafe(_notify_playback_failed(voice_client, track), loop)
        asyncio.run_coroutine_threadsafe(_track_playback_outcome(voice_client, failed=failed), loop)
        asyncio.run_coroutine_threadsafe(play_next(voice_client), loop)

    voice_client.play(source, after=_after)
    await status_panel.refresh(voice_client)


async def _notify_playback_failed(voice_client: discord.VoiceClient, track: Track) -> None:
    channel = status_panel.get_channel(voice_client.guild.id)
    if channel is None:
        return
    try:
        await channel.send(f"Couldn't play **{track.title}** - skipping.")
    except discord.HTTPException:
        logger.warning("Failed to post playback-failure notice for guild %s", voice_client.guild.id)


async def _enqueue(voice_client: discord.VoiceClient, track: Track, *, priority: bool) -> None:
    guild_queue = queues.get(voice_client.guild.id)
    if priority:
        guild_queue.add_priority(track)
    else:
        guild_queue.add_ambient(track)
    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next(voice_client)
    else:
        await status_panel.refresh(voice_client)


async def enqueue_priority(voice_client: discord.VoiceClient, track: Track) -> None:
    """Explicit /play requests - always played before any ambient tracks."""
    await _enqueue(voice_client, track, priority=True)


async def enqueue_ambient(voice_client: discord.VoiceClient, track: Track) -> None:
    """Tracks auto-queued by the natural-language agent - yield to /play requests."""
    await _enqueue(voice_client, track, priority=False)


async def pause(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_playing():
        voice_client.pause()
        start_idle_timer(voice_client)
        await status_panel.refresh(voice_client)
        return True
    return False


async def resume(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_paused():
        voice_client.resume()
        cancel_idle_timer(voice_client.guild.id)
        await status_panel.refresh(voice_client)
        return True
    return False


def skip(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        return True
    return False
