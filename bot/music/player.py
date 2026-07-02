import asyncio
import io
import logging
import time
from dataclasses import dataclass

import discord

from bot.config import settings
from bot.music import lyrics, status_panel
from bot.music.queue import GuildQueue, queues
from bot.music.youtube import FFMPEG_OPTIONS, Track, resolve_stream_url

logger = logging.getLogger(__name__)

_idle_timers: dict[int, asyncio.Task] = {}

# How often the synced-lyrics ticker checks playback position and (if the
# current line has advanced) edits the panel. A couple of seconds is close
# enough to feel "synced" without hammering Discord's edit rate limit.
_LYRIC_TICK_INTERVAL_SECONDS = 2

_lyric_tickers: dict[int, asyncio.Task] = {}


@dataclass
class _PlaybackPosition:
    started_at: float
    paused_at: float | None = None
    accumulated_pause: float = 0.0

    def elapsed(self) -> float:
        end = self.paused_at if self.paused_at is not None else time.monotonic()
        return end - self.started_at - self.accumulated_pause


# discord.py's VoiceClient exposes no "current playback position" - tracked
# by hand here so the lyrics ticker knows which line is "now".
_playback_positions: dict[int, _PlaybackPosition] = {}


def _start_playback_position(guild_id: int) -> None:
    _playback_positions[guild_id] = _PlaybackPosition(started_at=time.monotonic())


def _pause_playback_position(guild_id: int) -> None:
    position = _playback_positions.get(guild_id)
    if position is not None and position.paused_at is None:
        position.paused_at = time.monotonic()


def _resume_playback_position(guild_id: int) -> None:
    position = _playback_positions.get(guild_id)
    if position is not None and position.paused_at is not None:
        position.accumulated_pause += time.monotonic() - position.paused_at
        position.paused_at = None


def _clear_playback_position(guild_id: int) -> None:
    _playback_positions.pop(guild_id, None)


def _cancel_lyric_ticker(guild_id: int) -> None:
    task = _lyric_tickers.pop(guild_id, None)
    if task is not None:
        task.cancel()


def _start_lyric_ticker(voice_client: discord.VoiceClient, track: Track, lines: list[lyrics.LyricLine]) -> None:
    guild_id = voice_client.guild.id
    _cancel_lyric_ticker(guild_id)
    _lyric_tickers[guild_id] = asyncio.create_task(_tick_lyrics(voice_client, track, lines))


async def _tick_lyrics(voice_client: discord.VoiceClient, track: Track, lines: list[lyrics.LyricLine]) -> None:
    guild_id = voice_client.guild.id
    last_line: lyrics.LyricLine | None = None
    while True:
        await asyncio.sleep(_LYRIC_TICK_INTERVAL_SECONDS)
        if not voice_client.is_connected() or queues.get(guild_id).now_playing is not track:
            return
        position = _playback_positions.get(guild_id)
        if position is None:
            return
        line = lyrics.current_line(lines, position.elapsed())
        if line is not None and line is not last_line:
            last_line = line
            await status_panel.update_lyric_line(voice_client, line.text)


async def _load_lyrics_and_start_ticking(voice_client: discord.VoiceClient, track: Track) -> None:
    """Runs as a background task alongside playback - fetching lyrics is a
    network call and must never delay audio actually starting."""
    lines = await lyrics.fetch_synced_lyrics(track)
    if not lines:
        return
    guild_id = voice_client.guild.id
    if queues.get(guild_id).now_playing is not track:
        return  # track changed/ended while the lookup was in flight
    _start_lyric_ticker(voice_client, track, lines)


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


def cancel_idle_timer(guild_id: int) -> None:
    task = _idle_timers.pop(guild_id, None)
    if task is not None:
        task.cancel()


async def _cleanup_session(guild_id: int, *, reason: str | None = None) -> None:
    cancel_idle_timer(guild_id)
    _cancel_lyric_ticker(guild_id)
    _clear_playback_position(guild_id)
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

    guild_id = voice_client.guild.id
    guild_queue: GuildQueue = queues.get(guild_id)
    track = guild_queue.pop_next()
    if track is None:
        _cancel_lyric_ticker(guild_id)
        _clear_playback_position(guild_id)
        start_idle_timer(voice_client)
        await status_panel.refresh(voice_client)
        return

    cancel_idle_timer(guild_id)
    _cancel_lyric_ticker(guild_id)
    _start_playback_position(guild_id)
    await status_panel.clear_lyric_line(guild_id)

    stream_url, before_options = await resolve_stream_url(track)
    stderr_buffer = io.BytesIO()
    source = discord.FFmpegPCMAudio(
        stream_url,
        before_options=before_options,
        options=FFMPEG_OPTIONS,
        stderr=stderr_buffer,
    )

    loop = asyncio.get_running_loop()

    def _after(error: Exception | None) -> None:
        stderr_text = stderr_buffer.getvalue().decode(errors="replace")
        if _playback_likely_failed(error, stderr_text):
            logger.error(
                "Playback error for %s: %s\n%s", track.title, error, stderr_text[-_STDERR_LOG_TAIL:]
            )
            asyncio.run_coroutine_threadsafe(_notify_playback_failed(voice_client, track), loop)
        asyncio.run_coroutine_threadsafe(play_next(voice_client), loop)

    voice_client.play(source, after=_after)
    await status_panel.refresh(voice_client)
    asyncio.create_task(_load_lyrics_and_start_ticking(voice_client, track))


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
        _pause_playback_position(voice_client.guild.id)
        start_idle_timer(voice_client)
        await status_panel.refresh(voice_client)
        return True
    return False


async def resume(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_paused():
        voice_client.resume()
        _resume_playback_position(voice_client.guild.id)
        cancel_idle_timer(voice_client.guild.id)
        await status_panel.refresh(voice_client)
        return True
    return False


def skip(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        return True
    return False
