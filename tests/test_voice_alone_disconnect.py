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


def _own_bot_setup(bot_user_id: int = 999) -> tuple:
    bot_mock = MagicMock()
    bot_mock.user.id = bot_user_id
    cog = VoiceCog(bot=bot_mock)
    guild = SimpleNamespace(id=555, voice_client=MagicMock())
    own_member = MagicMock(spec=discord.Member)
    own_member.id = bot_user_id
    own_member.bot = True
    own_member.guild = guild
    return cog, own_member


async def test_cleans_up_when_bot_itself_is_disconnected_externally():
    # e.g. someone right-click-disconnects the bot, or it's moved somewhere it
    # can't follow - this never goes through /leave or the idle timeout, so
    # nothing else would clean up the panel/queue/timer without this.
    cog, own_member = _own_bot_setup()
    channel = _channel([])

    with patch(
        "bot.commands.voice.player.cleanup_after_external_disconnect", new=AsyncMock()
    ) as mock_cleanup:
        await cog.on_voice_state_update(own_member, _voice_state(channel), _voice_state(None))

    mock_cleanup.assert_awaited_once_with(555)


async def test_does_not_clean_up_when_bot_moves_between_channels():
    cog, own_member = _own_bot_setup()
    old_channel = _channel([])
    new_channel = _channel([])

    with patch(
        "bot.commands.voice.player.cleanup_after_external_disconnect", new=AsyncMock()
    ) as mock_cleanup:
        await cog.on_voice_state_update(
            own_member, _voice_state(old_channel), _voice_state(new_channel)
        )

    mock_cleanup.assert_not_awaited()


async def test_does_not_clean_up_on_mute_or_deafen_toggle():
    cog, own_member = _own_bot_setup()
    channel = _channel([])

    with patch(
        "bot.commands.voice.player.cleanup_after_external_disconnect", new=AsyncMock()
    ) as mock_cleanup:
        await cog.on_voice_state_update(own_member, _voice_state(channel), _voice_state(channel))

    mock_cleanup.assert_not_awaited()


async def test_bots_own_voice_state_change_does_not_fall_through_to_alone_check():
    cog, own_member = _own_bot_setup()

    with (
        patch("bot.commands.voice.player.cleanup_after_external_disconnect", new=AsyncMock()),
        patch("bot.commands.voice.player.disconnect_and_cleanup", new=AsyncMock()) as mock_old_path,
    ):
        await cog.on_voice_state_update(own_member, _voice_state(None), _voice_state(None))

    mock_old_path.assert_not_awaited()
