import json

import discord
import ollama

from bot.agent.prompts import SYSTEM_PROMPT
from bot.agent.tools import VALID_TOOL_NAMES, execute_tool
from bot.config import settings

_client = ollama.AsyncClient(host=settings.ollama_host)

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

    if tool == "none" or tool not in VALID_TOOL_NAMES:
        return reply or "Done."

    arguments = {"query": decision.get("query", "")}
    return await execute_tool(tool, arguments, voice_client, requested_by)
