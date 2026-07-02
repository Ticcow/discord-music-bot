import json

import discord
import ollama

from bot.agent.prompts import SYSTEM_PROMPT
from bot.agent.tools import TOOL_SCHEMAS, execute_tool
from bot.config import settings

_client = ollama.AsyncClient(host=settings.ollama_host)
_TOOL_NAMES = {tool["function"]["name"] for tool in TOOL_SCHEMAS}

MAX_TOOL_ROUNDS = 4


def _extract_inline_tool_call(content: str) -> tuple[str, dict] | None:
    """Some small models write a tool call as JSON text instead of using the
    API's structured tool_calls field. Scan for a {"name": ..., "arguments": ...}
    object embedded in the reply and treat it as a tool call if found."""
    decoder = json.JSONDecoder()
    idx = content.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(content, idx)
        except json.JSONDecodeError:
            idx = content.find("{", idx + 1)
            continue
        if isinstance(obj, dict) and obj.get("name") in _TOOL_NAMES and isinstance(
            obj.get("arguments"), dict
        ):
            return obj["name"], obj["arguments"]
        idx = content.find("{", idx + 1)
    return None


async def ask(
    user_message: str,
    voice_client: discord.VoiceClient | None,
    requested_by: str,
) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        response = await _client.chat(
            model=settings.ollama_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        message = response["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            content = (message.get("content") or "").strip()
            inline_call = _extract_inline_tool_call(content)
            if inline_call is None:
                return content or "Done."
            name, arguments = inline_call
            return await execute_tool(name, arguments, voice_client, requested_by)

        for call in tool_calls:
            function = call["function"]
            result = await execute_tool(
                function["name"], function.get("arguments", {}), voice_client, requested_by
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_name": function["name"],
                    "content": result,
                }
            )

    return "I ran into trouble finishing that request - try a plain /play command instead."
