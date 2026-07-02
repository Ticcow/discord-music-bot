import asyncio
import json
import logging

import discord
import ollama

from bot.agent.prompts import SYSTEM_PROMPT
from bot.agent.tools import VALID_TOOL_NAMES, execute_tool
from bot.config import settings

logger = logging.getLogger(__name__)

_client = ollama.AsyncClient(host=settings.ollama_host)

# Ollama on a 4GB Pi can only comfortably run one completion at a time -
# concurrent /ask calls would compete for the same limited RAM/CPU. Serialize
# completions globally rather than letting them race each other.
_chat_lock = asyncio.Lock()

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": list(VALID_TOOL_NAMES)},
        "query": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["tool", "query", "reply"],
}


async def ask(
    user_message: str,
    voice_client: discord.VoiceClient | None,
    requested_by: str,
) -> str:
    async with _chat_lock:
        response = await _client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            format=RESPONSE_SCHEMA,
        )

    try:
        decision = json.loads(response["message"].get("content") or "{}")
    except json.JSONDecodeError:
        return "I didn't quite catch that - try a plain /play command instead."

    tool = decision.get("tool", "none")
    reply = (decision.get("reply") or "").strip()
    # Log the derived decision, not the raw user message - the bot's privacy
    # posture is that message content is never logged or stored.
    logger.info("ask decision: tool=%s query=%r", tool, decision.get("query", ""))

    if tool == "none" or tool not in VALID_TOOL_NAMES:
        return reply or "Done."

    arguments = {"query": decision.get("query", "")}
    return await execute_tool(tool, arguments, voice_client, requested_by)
