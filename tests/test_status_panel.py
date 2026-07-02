import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.music import status_panel
from bot.music.queue import queues
from bot.music.youtube import Track


def _not_found() -> discord.NotFound:
    return discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")


def _server_error() -> discord.HTTPException:
    return discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "boom")


def _track(title: str) -> Track:
    return Track(
        title=title, webpage_url=f"https://x/{title}", duration=180, uploader=None,
        requested_by="tester",
    )


def _fake_channel() -> MagicMock:
    channel = MagicMock()
    channel.send = AsyncMock()
    return channel


def _fake_message(channel: MagicMock) -> MagicMock:
    message = MagicMock()
    message.channel = channel
    message.delete = AsyncMock()
    return message


def _fake_voice_client(guild_id: int, *, paused: bool = False) -> MagicMock:
    voice_client = MagicMock()
    voice_client.guild = SimpleNamespace(id=guild_id)
    voice_client.is_paused.return_value = paused
    return voice_client


def _panel_like_message(*, author) -> MagicMock:
    message = MagicMock()
    message.author = author
    message.embeds = [SimpleNamespace(title=status_panel.PANEL_EMBED_TITLE)]
    message.delete = AsyncMock()
    return message


def _plain_message(*, author) -> MagicMock:
    message = MagicMock()
    message.author = author
    message.embeds = []
    message.delete = AsyncMock()
    return message


def _fake_history(messages: list):
    class _HistoryIterator:
        def __init__(self, msgs):
            self._iter = iter(msgs)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    def _history(*, limit=None):
        return _HistoryIterator(messages)

    return _history


def _fake_history_raising(exc: Exception):
    class _HistoryIterator:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise exc

    def _history(*, limit=None):
        return _HistoryIterator()

    return _history


def setup_function() -> None:
    status_panel._panels.clear()


async def test_ensure_panel_only_posts_once():
    guild_id = 101
    channel = _fake_channel()
    channel.send.return_value = _fake_message(channel)

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.ensure_panel(channel, guild_id)

    channel.send.assert_awaited_once()


async def test_refresh_reposts_panel_as_a_new_message_at_the_bottom():
    guild_id = 102
    queues.get(guild_id).now_playing = _track("Now Playing Song")
    channel = _fake_channel()
    old_message = _fake_message(channel)
    new_message = _fake_message(channel)
    channel.send.side_effect = [old_message, new_message]

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.refresh(_fake_voice_client(guild_id))

    assert channel.send.await_count == 2
    old_message.delete.assert_awaited_once()
    assert status_panel._panels[guild_id] is new_message
    embed = channel.send.call_args.kwargs["embed"]
    assert "Now Playing Song" in embed.fields[0].value


def test_build_embed_includes_catjam_thumbnail():
    embed = status_panel._build_embed(107, is_paused=False)
    assert embed.thumbnail.url == status_panel.CATJAM_GIF_URL


def test_build_embed_includes_command_help_footer():
    embed = status_panel._build_embed(108, is_paused=False)
    assert embed.footer.text == status_panel.HELP_FOOTER_TEXT


async def test_ensure_panel_swallows_permission_errors():
    # If the bot lacks Send Messages/Embed Links in the channel, ensure_panel must not
    # raise - an unhandled exception here previously aborted /play entirely, leaving the
    # interaction stuck on "thinking..." forever and the bot connected to voice with no
    # idle timer.
    guild_id = 106
    channel = _fake_channel()
    channel.send.side_effect = _server_error()

    await status_panel.ensure_panel(channel, guild_id)  # should not raise

    assert guild_id not in status_panel._panels


async def test_ensure_panel_deletes_stale_panels_left_over_from_before_a_restart():
    # A bot restart wipes _panels but not the message actually sitting in the
    # channel - without this, every restart would need the manual cleanup
    # this replaces.
    guild_id = 111
    channel = _fake_channel()
    channel.send.return_value = _fake_message(channel)
    bot_member = MagicMock()
    channel.guild.me = bot_member
    stale_panel = _panel_like_message(author=bot_member)
    unrelated_message = _plain_message(author=MagicMock())
    channel.history = _fake_history([unrelated_message, stale_panel])

    await status_panel.ensure_panel(channel, guild_id)

    stale_panel.delete.assert_awaited_once()
    unrelated_message.delete.assert_not_awaited()


async def test_ensure_panel_ignores_panel_like_embeds_from_other_authors():
    guild_id = 112
    channel = _fake_channel()
    channel.send.return_value = _fake_message(channel)
    bot_member = MagicMock()
    channel.guild.me = bot_member
    someone_elses_message = _panel_like_message(author=MagicMock())
    channel.history = _fake_history([someone_elses_message])

    await status_panel.ensure_panel(channel, guild_id)

    someone_elses_message.delete.assert_not_awaited()


async def test_ensure_panel_tolerates_missing_history_permission():
    guild_id = 113
    channel = _fake_channel()
    channel.send.return_value = _fake_message(channel)
    channel.history = _fake_history_raising(
        discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Permissions")
    )

    await status_panel.ensure_panel(channel, guild_id)  # should not raise

    assert guild_id in status_panel._panels


async def test_ensure_panel_does_not_scan_history_when_a_panel_is_already_tracked():
    guild_id = 114
    channel = _fake_channel()
    channel.send.return_value = _fake_message(channel)
    await status_panel.ensure_panel(channel, guild_id)

    channel.history = MagicMock(side_effect=AssertionError("history should not be called"))
    await status_panel.ensure_panel(channel, guild_id)

    channel.send.assert_awaited_once()


async def test_refresh_is_a_noop_when_no_panel_exists():
    await status_panel.refresh(_fake_voice_client(999))  # should not raise


async def test_refresh_ignores_not_found_when_deleting_old_message():
    # The old panel message may already be gone (deleted by a user, etc.).
    guild_id = 103
    channel = _fake_channel()
    old_message = _fake_message(channel)
    old_message.delete = AsyncMock(side_effect=_not_found())
    new_message = _fake_message(channel)
    channel.send.side_effect = [old_message, new_message]

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.refresh(_fake_voice_client(guild_id))  # should not raise

    assert status_panel._panels[guild_id] is new_message


async def test_refresh_keeps_old_panel_if_repost_fails():
    guild_id = 105
    channel = _fake_channel()
    old_message = _fake_message(channel)
    channel.send.side_effect = [old_message, _server_error()]

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.refresh(_fake_voice_client(guild_id))

    assert status_panel._panels[guild_id] is old_message
    old_message.delete.assert_not_awaited()


async def test_refresh_serializes_concurrent_calls_without_orphaning_a_message():
    # Regression: if a track fails almost instantly, play_next() can run
    # twice back to back, triggering two overlapping refresh() calls. Without
    # locking, both could read the same "old" message, post their own new
    # one, and only the last write to _panels[guild_id] survives - silently
    # orphaning whichever message lost the race, with no code path left that
    # will ever delete it.
    guild_id = 110
    channel = _fake_channel()
    initial_message = _fake_message(channel)
    posted = [initial_message]

    async def _send(*, embed):
        await asyncio.sleep(0.01)
        message = _fake_message(channel)
        posted.append(message)
        return message

    channel.send = AsyncMock(side_effect=[initial_message])
    await status_panel.ensure_panel(channel, guild_id)

    channel.send = AsyncMock(side_effect=_send)
    voice_client = _fake_voice_client(guild_id)
    await asyncio.gather(status_panel.refresh(voice_client), status_panel.refresh(voice_client))

    current = status_panel._panels[guild_id]
    for message in posted:
        if message is current:
            message.delete.assert_not_awaited()
        else:
            message.delete.assert_awaited_once()


async def test_clear_panel_deletes_message_and_allows_recreation():
    guild_id = 104
    channel = _fake_channel()
    message = _fake_message(channel)
    channel.send.return_value = message

    await status_panel.ensure_panel(channel, guild_id)
    await status_panel.clear_panel(guild_id)

    message.delete.assert_awaited_once()
    assert guild_id not in status_panel._panels
