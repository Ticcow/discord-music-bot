import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXTENSIONS = (
    "bot.commands.voice",
    "bot.commands.playback",
    "bot.commands.chat",
)


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        # Track titles come from YouTube video metadata, which is entirely
        # attacker-controlled (anyone can upload a video titled "<@user_id>"),
        # and titles get echoed back into plain message content in /queue, /play,
        # and /ask replies. Block @everyone/roles/arbitrary user pings globally so
        # a malicious title can't ping anyone; keep replied_user so @mention chat
        # still notifies the person the bot is actually replying to.
        allowed_mentions = discord.AllowedMentions(
            everyone=False, users=False, roles=False, replied_user=True
        )
        super().__init__(
            command_prefix="!", intents=intents, allowed_mentions=allowed_mentions
        )

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.tree.on_error = self.on_app_command_error
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (id=%s)", self.user, self.user.id)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Fallback for any exception a slash command doesn't handle itself. Without this,
        an unhandled error after interaction.response.defer() leaves the user staring at
        a "thinking..." message forever, since nothing ever sends a followup."""
        command_name = interaction.command.name if interaction.command else "unknown"
        logger.error("Unhandled error in /%s", command_name, exc_info=error)

        message = "Something went wrong running that command. Please try again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.warning("Could not notify the user about a command error")


async def main() -> None:
    bot = MusicBot()
    async with bot:
        await bot.start(settings.discord_bot_token)


if __name__ == "__main__":
    asyncio.run(main())
