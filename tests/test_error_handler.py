from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from discord import app_commands

from bot.main import MusicBot


def _server_error() -> discord.HTTPException:
    return discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "boom")


def _interaction(*, responded: bool) -> MagicMock:
    interaction = MagicMock()
    interaction.command = SimpleNamespace(name="play")
    interaction.response.is_done.return_value = responded
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def test_sends_initial_response_when_interaction_not_yet_responded():
    # Reproduces the /play "stuck thinking" bug: an unhandled exception after defer()
    # left the interaction with no followup at all. This must always give the user
    # some response, whichever form the interaction is in.
    interaction = _interaction(responded=False)

    await MusicBot.on_app_command_error(MagicMock(), interaction, app_commands.AppCommandError("boom"))

    interaction.response.send_message.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()


async def test_sends_followup_when_interaction_already_deferred():
    interaction = _interaction(responded=True)

    await MusicBot.on_app_command_error(MagicMock(), interaction, app_commands.AppCommandError("boom"))

    interaction.followup.send.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()


async def test_swallows_failure_to_notify_the_user():
    interaction = _interaction(responded=True)
    interaction.followup.send.side_effect = _server_error()

    await MusicBot.on_app_command_error(
        MagicMock(), interaction, app_commands.AppCommandError("boom")
    )  # should not raise


async def test_handles_missing_command_name():
    interaction = _interaction(responded=False)
    interaction.command = None

    await MusicBot.on_app_command_error(
        MagicMock(), interaction, app_commands.AppCommandError("boom")
    )  # should not raise

    interaction.response.send_message.assert_awaited_once()
