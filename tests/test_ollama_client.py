import json
from unittest.mock import AsyncMock, patch

from bot.agent.ollama_client import ask


def _chat_response(content: dict | str) -> dict:
    text = content if isinstance(content, str) else json.dumps(content)
    return {"message": {"content": text}}


async def test_ask_executes_tool_call_and_returns_its_result():
    decision = {"tool": "search_and_play", "query": "early kanye west", "reply": "ignored"}
    voice_client = object()

    with (
        patch("bot.agent.ollama_client._client") as mock_client,
        patch(
            "bot.agent.ollama_client.execute_tool",
            new=AsyncMock(return_value="Queued 'Through the Wire'."),
        ) as mock_execute,
    ):
        mock_client.chat = AsyncMock(return_value=_chat_response(decision))
        result = await ask("play some early kanye", voice_client, requested_by="tester")

    assert result == "Queued 'Through the Wire'."
    mock_execute.assert_awaited_once_with(
        "search_and_play", {"query": "early kanye west"}, voice_client, "tester"
    )


async def test_ask_returns_reply_directly_when_tool_is_none():
    decision = {"tool": "none", "query": "", "reply": "I'm just a music bot!"}

    with (
        patch("bot.agent.ollama_client._client") as mock_client,
        patch("bot.agent.ollama_client.execute_tool", new=AsyncMock()) as mock_execute,
    ):
        mock_client.chat = AsyncMock(return_value=_chat_response(decision))
        result = await ask("how are you", object(), requested_by="tester")

    assert result == "I'm just a music bot!"
    mock_execute.assert_not_awaited()


async def test_ask_falls_back_gracefully_on_unparseable_content():
    # Regression test: qwen2.5:1.5b once narrated an action in plain text
    # ("Searching for early Kanye West tracks...") without emitting any
    # parseable tool call, silently doing nothing while sounding like it
    # had. Structured output is meant to make this impossible, but the
    # fallback must still degrade honestly if a future model regresses.
    with (
        patch("bot.agent.ollama_client._client") as mock_client,
        patch("bot.agent.ollama_client.execute_tool", new=AsyncMock()) as mock_execute,
    ):
        mock_client.chat = AsyncMock(
            return_value=_chat_response("Searching for early Kanye West tracks...")
        )
        result = await ask("play some early kanye", object(), requested_by="tester")

    assert "try a plain /play command" in result
    mock_execute.assert_not_awaited()


async def test_ask_falls_back_when_tool_name_is_unrecognized():
    decision = {"tool": "delete_everything", "query": "", "reply": "uh oh"}

    with (
        patch("bot.agent.ollama_client._client") as mock_client,
        patch("bot.agent.ollama_client.execute_tool", new=AsyncMock()) as mock_execute,
    ):
        mock_client.chat = AsyncMock(return_value=_chat_response(decision))
        result = await ask("test", object(), requested_by="tester")

    assert result == "uh oh"
    mock_execute.assert_not_awaited()


async def test_ask_defaults_to_done_when_reply_is_missing():
    decision = {"tool": "none", "query": ""}

    with (
        patch("bot.agent.ollama_client._client") as mock_client,
        patch("bot.agent.ollama_client.execute_tool", new=AsyncMock()) as mock_execute,
    ):
        mock_client.chat = AsyncMock(return_value=_chat_response(decision))
        result = await ask("test", object(), requested_by="tester")

    assert result == "Done."
    mock_execute.assert_not_awaited()
