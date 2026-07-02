import logging

import discord

from bot.music.queue import queues

logger = logging.getLogger(__name__)

_panels: dict[int, discord.Message] = {}

CATJAM_GIF_URL = "https://media.tenor.com/hKxzQiQ8GMgAAAAj/cat-jam-cat.gif"

HELP_FOOTER_TEXT = (
    "/play, /pause, /resume, /skip, /queue, /lyrics - or just /ask in plain English"
)


def _build_embed(guild_id: int, is_paused: bool) -> discord.Embed:
    guild_queue = queues.get(guild_id)
    embed = discord.Embed(title="DJ OLLAMA", color=discord.Color.blurple())
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


async def ensure_panel(channel: discord.abc.Messageable, guild_id: int) -> None:
    """Post the live panel the first time a guild starts using voice. No-op if one already exists.
    Swallows permission errors so a channel the bot can't post in doesn't block playback."""
    if guild_id in _panels:
        return
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
