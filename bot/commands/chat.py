import discord
from discord import app_commands
from discord.ext import commands

from bot.agent.ollama_client import ask
from bot.music.player import ensure_voice_client


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ask", description="Talk to the music bot in natural language")
    @app_commands.describe(message="What do you want to do? e.g. 'play something chill'")
    async def ask_command(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.response.defer()

        voice_client = await ensure_voice_client(interaction)
        reply = await ask(message, voice_client, requested_by=interaction.user.display_name)
        await interaction.followup.send(reply)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.bot.user not in message.mentions:
            return

        content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
        content = content.replace(f"<@!{self.bot.user.id}>", "").strip()
        if not content:
            return

        voice_client = message.guild.voice_client if message.guild else None
        async with message.channel.typing():
            reply = await ask(content, voice_client, requested_by=message.author.display_name)
        await message.reply(reply)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatCog(bot))
