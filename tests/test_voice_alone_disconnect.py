from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from bot.commands.voice import VoiceCog


def _channel(members: list) -> MagicMock:
    # Plain MagicMock so equality is by identity, unlike SimpleNamespace
    # (which compares __dict__ contents - two channels with the same
    # member list would otherwise compare equal by accident).
    channel = MagicMock()
    channel.members = members
    return channel


def _voice_state(channel) -> SimpleNamespace:
    return SimpleNamespace(channel=channel)


def _member(*, bot: bool, guild=None) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.bot = bot
    member.guild = guild
    return member


async def _run(member, before_channel, after_channel) -> AsyncMock:
    cog = VoiceCog(bot=MagicMock())
    with patch(
        "bot.commands.voice.player.disconnect_and_cleanup", new=AsyncMock()
    ) as mock_cleanup:
        await cog.on_voice_state_update(
            member, _voice_state(before_channel), _voice_state(after_channel)
        )
    return mock_cleanup


async def test_disconnects_when_last_human_leaves():
    bot_member = _member(bot=True)
    channel = _channel([bot_member])
    voice_client = MagicMock(channel=channel)
    guild = SimpleNamespace(voice_client=voice_client)
    leaving_member = _member(bot=False, guild=guild)

    mock_cleanup = await _run(leaving_member, channel, None)

    mock_cleanup.assert_awaited_once()


async def test_does_not_disconnect_when_humans_remain():
    other_human = _member(bot=False)
    channel = _channel([other_human])
    voice_client = MagicMock(channel=channel)
    guild = SimpleNamespace(voice_client=voice_client)
    leaving_member = _member(bot=False, guild=guild)

    mock_cleanup = await _run(leaving_member, channel, None)

    mock_cleanup.assert_not_awaited()


async def test_ignores_bot_members_leaving():
    channel = _channel([])
    voice_client = MagicMock(channel=channel)
    guild = SimpleNamespace(voice_client=voice_client)
    leaving_bot = _member(bot=True, guild=guild)

    mock_cleanup = await _run(leaving_bot, channel, None)

    mock_cleanup.assert_not_awaited()


async def test_ignores_changes_unrelated_to_bots_channel():
    bot_channel = _channel([])
    other_channel = _channel([])
    voice_client = MagicMock(channel=bot_channel)
    guild = SimpleNamespace(voice_client=voice_client)
    member = _member(bot=False, guild=guild)

    mock_cleanup = await _run(member, other_channel, other_channel)

    mock_cleanup.assert_not_awaited()


async def test_noop_when_bot_not_in_voice():
    guild = SimpleNamespace(voice_client=None)
    member = _member(bot=False, guild=guild)

    mock_cleanup = await _run(member, None, None)

    mock_cleanup.assert_not_awaited()
