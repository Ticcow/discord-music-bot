import discord

from bot.music.queue import queues

_panels: dict[int, discord.Message] = {}


def _build_embed(guild_id: int, is_paused: bool) -> discord.Embed:
    guild_queue = queues.get(guild_id)
    embed = discord.Embed(title="DJ OLLAMA", color=discord.Color.blurple())

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
    """Post the live panel the first time a guild starts using voice. No-op if one already exists."""
    if guild_id in _panels:
        return
    message = await channel.send(embed=_build_embed(guild_id, is_paused=False))
    _panels[guild_id] = message


async def refresh(voice_client: discord.VoiceClient) -> None:
    message = _panels.get(voice_client.guild.id)
    if message is None:
        return
    embed = _build_embed(voice_client.guild.id, is_paused=voice_client.is_paused())
    try:
        await message.edit(embed=embed)
    except discord.NotFound:
        _panels.pop(voice_client.guild.id, None)


async def clear_panel(guild_id: int) -> None:
    message = _panels.pop(guild_id, None)
    if message is None:
        return
    try:
        await message.delete()
    except discord.NotFound:
        pass
