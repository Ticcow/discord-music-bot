import asyncio
import logging

import discord

from bot.config import settings
from bot.music import status_panel
from bot.music.queue import GuildQueue, queues
from bot.music.youtube import FFMPEG_BEFORE_OPTIONS, FFMPEG_OPTIONS, Track, resolve_stream_url

logger = logging.getLogger(__name__)

_idle_timers: dict[int, asyncio.Task] = {}


def cancel_idle_timer(guild_id: int) -> None:
    task = _idle_timers.pop(guild_id, None)
    if task is not None:
        task.cancel()


async def _disconnect_after_idle(voice_client: discord.VoiceClient) -> None:
    try:
        await asyncio.sleep(settings.idle_timeout_seconds)
    except asyncio.CancelledError:
        return

    guild_id = voice_client.guild.id
    _idle_timers.pop(guild_id, None)
    if not voice_client.is_connected():
        return

    channel = status_panel.get_channel(guild_id)
    queues.get(guild_id).clear()
    await voice_client.disconnect()
    await status_panel.clear_panel(guild_id)
    if channel is not None:
        try:
            await channel.send("Left the voice channel after being idle for too long.")
        except discord.HTTPException:
            logger.warning("Failed to post idle-timeout notice for guild %s", guild_id)


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
    await status_panel.ensure_panel(interaction.channel, interaction.guild.id)
    start_idle_timer(voice_client)
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

    stream_url = await resolve_stream_url(track)
    source = discord.FFmpegPCMAudio(
        stream_url,
        before_options=FFMPEG_BEFORE_OPTIONS,
        options=FFMPEG_OPTIONS,
    )

    loop = asyncio.get_running_loop()

    def _after(error: Exception | None) -> None:
        if error:
            logger.error("Playback error for %s: %s", track.title, error)
        asyncio.run_coroutine_threadsafe(play_next(voice_client), loop)

    voice_client.play(source, after=_after)
    await status_panel.refresh(voice_client)


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
