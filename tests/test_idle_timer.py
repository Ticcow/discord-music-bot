import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.music import player, status_panel


def _fake_voice_client(guild_id: int) -> MagicMock:
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_connected.return_value = True
    voice_client.disconnect = AsyncMock()
    return voice_client


def setup_function() -> None:
    for task in player._idle_timers.values():
        task.cancel()
    player._idle_timers.clear()
    status_panel._panels.clear()


async def test_start_idle_timer_disconnects_after_timeout_elapses():
    guild_id = 201
    voice_client = _fake_voice_client(guild_id)

    with patch.object(player.settings, "idle_timeout_seconds", 0):
        player.start_idle_timer(voice_client)
        await asyncio.sleep(0.05)

    voice_client.disconnect.assert_awaited_once()
    assert guild_id not in player._idle_timers


async def test_cancel_idle_timer_prevents_disconnect():
    guild_id = 202
    voice_client = _fake_voice_client(guild_id)

    with patch.object(player.settings, "idle_timeout_seconds", 10):
        player.start_idle_timer(voice_client)
        player.cancel_idle_timer(guild_id)
        await asyncio.sleep(0.05)

    voice_client.disconnect.assert_not_awaited()
    assert guild_id not in player._idle_timers


async def test_start_idle_timer_replaces_any_existing_timer():
    guild_id = 203
    voice_client = _fake_voice_client(guild_id)

    with patch.object(player.settings, "idle_timeout_seconds", 10):
        player.start_idle_timer(voice_client)
        first_task = player._idle_timers[guild_id]
        player.start_idle_timer(voice_client)
        second_task = player._idle_timers[guild_id]

    assert first_task is not second_task
    player.cancel_idle_timer(guild_id)


async def test_disconnect_after_idle_posts_a_notice_in_the_panel_channel():
    guild_id = 204
    voice_client = _fake_voice_client(guild_id)
    channel = MagicMock()
    channel.send = AsyncMock()
    panel_message = MagicMock()
    panel_message.channel = channel
    panel_message.delete = AsyncMock()
    status_panel._panels[guild_id] = panel_message

    with patch.object(player.settings, "idle_timeout_seconds", 0):
        player.start_idle_timer(voice_client)
        await asyncio.sleep(0.05)

    channel.send.assert_awaited_once()
    assert guild_id not in status_panel._panels


async def test_disconnect_after_idle_does_nothing_if_already_disconnected():
    guild_id = 205
    voice_client = _fake_voice_client(guild_id)
    voice_client.is_connected.return_value = False

    with patch.object(player.settings, "idle_timeout_seconds", 0):
        player.start_idle_timer(voice_client)
        await asyncio.sleep(0.05)

    voice_client.disconnect.assert_not_awaited()
