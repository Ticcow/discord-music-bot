import discord
import ollama

from bot.agent.prompts import SYSTEM_PROMPT
from bot.agent.tools import TOOL_SCHEMAS, execute_tool
from bot.config import settings

_client = ollama.AsyncClient(host=settings.ollama_host)

MAX_TOOL_ROUNDS = 4


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
            return (message.get("content") or "").strip() or "Done."

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
