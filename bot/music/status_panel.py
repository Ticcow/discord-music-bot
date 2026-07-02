import asyncio
import logging

import discord

from bot.music.queue import queues

logger = logging.getLogger(__name__)

_panels: dict[int, discord.Message] = {}

# ensure_panel/refresh/clear_panel all read-then-write _panels[guild_id]. If a
# track fails almost instantly, play_next() can run twice in quick succession
# and race two refresh() calls: both post a new message, but only one gets
# tracked, leaving the other as a permanently orphaned duplicate panel. A
# per-guild lock serializes these so the second call always sees the first's
# result before acting.
_locks: dict[int, asyncio.Lock] = {}


def _lock_for(guild_id: int) -> asyncio.Lock:
    return _locks.setdefault(guild_id, asyncio.Lock())

CATJAM_GIF_URL = "https://media.tenor.com/hKxzQiQ8GMgAAAAj/cat-jam-cat.gif"

HELP_FOOTER_TEXT = (
    "/play, /pause, /resume, /skip, /queue, /lyrics - or just /ask in plain English"
)

PANEL_EMBED_TITLE = "DJ OLLAMA"

# How far back to look for leftover panels (e.g. posted before a bot restart,
# which wipes the in-memory _panels tracking but leaves the message sitting
# in the channel). Recent history only - not a full-channel scan.
_STALE_PANEL_SCAN_LIMIT = 50


def _build_embed(guild_id: int, is_paused: bool) -> discord.Embed:
    guild_queue = queues.get(guild_id)
    embed = discord.Embed(title=PANEL_EMBED_TITLE, color=discord.Color.blurple())
    embed.set_thumbnail(url=CATJAM_GIF_URL)
    embed.set_footer(text=HELP_FOOTER_TEXT)

    if guild_queue.now_playing:
        status = "Paused" if is_paused else "Now Playing"
        track = guild_queue.now_playing
        embed.add_field(
            name=status,
            value=f"{track.title}\n*requested by {track.requested_by}*",
            inline=False,
        )
    else:
        embed.add_field(name="Now Playing", value="Nothing is playing.", inline=False)

    upcoming = guild_queue.peek_all()
    if upcoming:
        lines = "\n".join(f"{i + 1}. {t.title}" for i, t in enumerate(upcoming[:10]))
        embed.add_field(name="Up Next", value=lines, inline=False)

    return embed


async def _delete_stale_panels(channel: discord.abc.Messageable) -> None:
    """Delete any leftover panel messages sitting in the channel that we're not
    currently tracking - most commonly because the bot restarted and the
    in-memory _panels dict was wiped, but the old message never got cleaned up."""
    me = getattr(getattr(channel, "guild", None), "me", None)
    try:
        async for message in channel.history(limit=_STALE_PANEL_SCAN_LIMIT):
            if me is not None and message.author != me:
                continue
            if not message.embeds or message.embeds[0].title != PANEL_EMBED_TITLE:
                continue
            try:
                await message.delete()
            except discord.HTTPException:
                pass
    except discord.HTTPException:
        logger.warning("Failed to scan for stale status panels")


async def ensure_panel(channel: discord.abc.Messageable, guild_id: int) -> None:
    """Post the live panel the first time a guild starts using voice. No-op if one already exists.
    Swallows permission errors so a channel the bot can't post in doesn't block playback."""
    async with _lock_for(guild_id):
        if guild_id in _panels:
            return
        await _delete_stale_panels(channel)
        try:
            message = await channel.send(embed=_build_embed(guild_id, is_paused=False))
        except discord.HTTPException:
            logger.warning("Failed to post status panel for guild %s", guild_id)
            return
        _panels[guild_id] = message


async def refresh(voice_client: discord.VoiceClient) -> None:
    """Repost the panel as a new message so it stays at the bottom of the
    channel (the most recent message) instead of sinking under newer chat
    as an edited-in-place message would."""
    guild_id = voice_client.guild.id
    async with _lock_for(guild_id):
        old_message = _panels.get(guild_id)
        if old_message is None:
            return

        embed = _build_embed(guild_id, is_paused=voice_client.is_paused())
        try:
            new_message = await old_message.channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to repost status panel for guild %s", guild_id)
            return

        _panels[guild_id] = new_message
        try:
            await old_message.delete()
        except discord.NotFound:
            pass


async def clear_panel(guild_id: int) -> None:
    async with _lock_for(guild_id):
        message = _panels.pop(guild_id, None)
        if message is None:
            return
        try:
            await message.delete()
        except discord.NotFound:
            pass


def get_channel(guild_id: int) -> discord.abc.Messageable | None:
    """The panel's text channel, if one exists - useful for posting a note there
    (e.g. an idle-timeout notice) before the panel itself is cleared."""
    message = _panels.get(guild_id)
    return message.channel if message else None
