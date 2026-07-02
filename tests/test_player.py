from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.music import player, status_panel
from bot.music.player import is_authorized


def _member(channel_id: int | None) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.voice = None if channel_id is None else SimpleNamespace(channel=SimpleNamespace(id=channel_id))
    return member


def _voice_client(channel_id: int) -> MagicMock:
    voice_client = MagicMock()
    voice_client.channel = SimpleNamespace(id=channel_id)
    return voice_client


def test_authorized_when_no_active_session():
    # No session yet - anyone can start one wherever they are.
    assert is_authorized(None, _member(channel_id=42)) is True


def test_authorized_when_member_in_same_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=1)) is True


def test_not_authorized_when_member_in_different_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=2)) is False


def test_not_authorized_when_member_not_in_any_voice_channel():
    voice_client = _voice_client(channel_id=1)
    assert is_authorized(voice_client, _member(channel_id=None)) is False


def test_not_authorized_when_not_a_guild_member():
    # e.g. a DM context where .voice doesn't exist at all.
    voice_client = _voice_client(channel_id=1)
    plain_user = MagicMock(spec=discord.User)
    assert is_authorized(voice_client, plain_user) is False


def setup_function() -> None:
    for task in player._idle_timers.values():
        task.cancel()
    player._idle_timers.clear()


async def test_ensure_voice_client_starts_idle_timer_before_posting_panel():
    # start_idle_timer must run before the (fallible) panel post, so the bot is never
    # left connected to voice with no cleanup timer if posting the panel goes wrong.
    guild_id = 301
    new_voice_client = MagicMock()
    new_voice_client.guild = SimpleNamespace(id=guild_id)

    channel = MagicMock()
    channel.connect = AsyncMock(return_value=new_voice_client)
    member = MagicMock(spec=discord.Member)
    member.voice = SimpleNamespace(channel=channel)

    interaction = MagicMock()
    interaction.guild = SimpleNamespace(voice_client=None, id=guild_id)
    interaction.user = member

    with patch.object(status_panel, "ensure_panel", new=AsyncMock(side_effect=RuntimeError("boom"))):
        try:
            await player.ensure_voice_client(interaction)
        except RuntimeError:
            pass

    assert guild_id in player._idle_timers
    player.cancel_idle_timer(guild_id)
