import discord

from bot.music import player
from bot.music.queue import queues
from bot.music.youtube import search_many

VALID_TOOL_NAMES = ("search_and_play", "pause", "resume", "skip", "list_queue", "none")

# Vibe/artist requests via /ask queue a short run of tracks rather than one,
# since the intent behind e.g. "play some kanye" is a listening session, not
# a single precise track. These sit behind any /play requests in the queue.
BATCH_SIZE = 3


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
            tracks = await search_many(query, BATCH_SIZE, requested_by=requested_by)
        except ValueError as exc:
            return str(exc)
        for track in tracks:
            await player.enqueue_ambient(voice_client, track)
        titles = ", ".join(f"'{t.title}'" for t in tracks)
        return f"Queued {len(tracks)} tracks: {titles}."

    if name == "pause":
        return "Paused." if await player.pause(voice_client) else "Nothing is playing."

    if name == "resume":
        return "Resumed." if await player.resume(voice_client) else "Nothing is paused."

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
