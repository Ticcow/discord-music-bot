import asyncio
import logging

import discord

from bot.music import status_panel
from bot.music.queue import GuildQueue, queues
from bot.music.youtube import FFMPEG_BEFORE_OPTIONS, FFMPEG_OPTIONS, Track, resolve_stream_url

logger = logging.getLogger(__name__)


async def ensure_voice_client(interaction: discord.Interaction) -> discord.VoiceClient | None:
    """Return the guild's active voice client, connecting to the invoker's channel if needed."""
    voice_client = interaction.guild.voice_client
    if voice_client is not None:
        return voice_client

    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None:
        await interaction.response.send_message(
            "You need to be in a voice channel first.", ephemeral=True
        )
        return None

    voice_client = await member.voice.channel.connect()
    await status_panel.ensure_panel(interaction.channel, interaction.guild.id)
    return voice_client


async def play_next(voice_client: discord.VoiceClient) -> None:
    if not voice_client.is_connected():
        return

    guild_queue: GuildQueue = queues.get(voice_client.guild.id)
    track = guild_queue.pop_next()
    if track is None:
        await status_panel.refresh(voice_client)
        return

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
        await status_panel.refresh(voice_client)
        return True
    return False


async def resume(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_paused():
        voice_client.resume()
        await status_panel.refresh(voice_client)
        return True
    return False


def skip(voice_client: discord.VoiceClient) -> bool:
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
        return True
    return False
