import discord

from bot.music import player
from bot.music.queue import queues
from bot.music.youtube import search

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_and_play",
            "description": (
                "Search YouTube for a track and play it. If something is already playing, "
                "the track is added to the end of the queue instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A YouTube search query for the song, artist, or vibe requested.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause",
            "description": "Pause the currently playing track.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume",
            "description": "Resume a paused track.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip",
            "description": "Skip the currently playing track and move to the next queued track.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_queue",
            "description": "List the currently playing track and the upcoming queue.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


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
