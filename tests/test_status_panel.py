from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.music import status_panel
from bot.music.queue import queues
from bot.music.youtube import Track


def _not_found() -> discord.NotFound:
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")


def _track(title: str) -> Track:
    return Track(
        title=title, webpage_url=f"https://x/{title}", duration=180, uploader=None,
        requested_by="tester",
    )


def _fake_channel(message: discord.Message) -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock(return_value=message)
    return channel


def _fake_voice_client(guild_id: int, *, paused: bool = False) -> MagicMock:
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_paused.return_value = paused
    return voice_client


def setup_function() -> None:
    status_panel._panels.clear()


async def test_ensure_panel_only_posts_once():
    guild_id = 101
    channel = _fake_channel(MagicMock())

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.ensure_panel(channel, guild_id)

    channel.send.assert_awaited_once()


async def test_refresh_edits_the_existing_panel():
    guild_id = 102
    queues.get(guild_id).now_playing = _track("Now Playing Song")
    message = MagicMock()
    message.edit = AsyncMock()
    channel = _fake_channel(message)

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.refresh(_fake_voice_client(guild_id))

    message.edit.assert_awaited_once()
    embed = message.edit.call_args.kwargs["embed"]
    assert "Now Playing Song" in embed.fields[0].value


async def test_refresh_is_a_noop_when_no_panel_exists():
    await status_panel.refresh(_fake_voice_client(999))  # should not raise


async def test_refresh_drops_panel_on_not_found_so_it_can_be_recreated():
    guild_id = 103
    message = MagicMock()
    message.edit = AsyncMock(side_effect=_not_found())
    channel = _fake_channel(message)

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.refresh(_fake_voice_client(guild_id))

    assert guild_id not in status_panel._panels

    await status_panel.ensure_panel(channel, guild_id)
    assert channel.send.await_count == 2


async def test_clear_panel_deletes_message_and_allows_recreation():
    guild_id = 104
    message = MagicMock()
    message.delete = AsyncMock()
    channel = _fake_channel(message)

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.clear_panel(guild_id)

    message.delete.assert_awaited_once()
    assert guild_id not in status_panel._panels
