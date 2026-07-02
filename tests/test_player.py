from types import SimpleNamespace
from unittest.mock import MagicMock

import discord

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
