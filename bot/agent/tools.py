import discord

from bot.music import player
from bot.music.queue import queues
from bot.music.youtube import search

VALID_TOOL_NAMES = ("search_and_play", "pause", "resume", "skip", "list_queue", "none")


async def execute_tool(
    name: str,
    arguments: dict,
    voice_client: discord.VoiceClient | None,
    requested_by: str,
) -> str:
    if voice_client is None:
        return "Not connected to a voice channel."

    if name == "search_and_play":
        query = arguments.get("query", "")
        try:
            track = await search(query, requested_by=requested_by)
        except ValueError as exc:
            return str(exc)
        await player.enqueue(voice_client, track)
        return f"Queued '{track.title}'."

    if name == "pause":
        return "Paused." if player.pause(voice_client) else "Nothing is playing."

    if name == "resume":
        return "Resumed." if player.resume(voice_client) else "Nothing is paused."

    if name == "skip":
        return "Skipped." if player.skip(voice_client) else "Nothing is playing."

    if name == "list_queue":
        guild_queue = queues.get(voice_client.guild.id)
        parts = []
        if guild_queue.now_playing:
            parts.append(f"Now playing: {guild_queue.now_playing.title}.")
        upcoming = guild_queue.peek_all()
        if upcoming:
            parts.append("Up next: " + ", ".join(t.title for t in upcoming) + ".")
        if not parts:
            parts.append("The queue is empty.")
        return " ".join(parts)

    return f"Unknown tool: {name}"
