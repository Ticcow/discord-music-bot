import discord
from discord import app_commands
from discord.ext import commands

from bot.music import player, status_panel
from bot.music.queue import queues


class VoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="join", description="Join your current voice channel")
    async def join(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or member.voice is None:
            await interaction.response.send_message(
                "You need to be in a voice channel first.", ephemeral=True
            )
            return

        channel = member.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await channel.connect()
            await status_panel.ensure_panel(interaction.channel, interaction.guild.id)
            player.start_idle_timer(voice_client)
            await interaction.response.send_message(f"Joined {channel.mention}.")
        elif voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
            await interaction.response.send_message(f"Moved to {channel.mention}.")
        else:
            await interaction.response.send_message("Already connected here.")

    @app_commands.command(name="leave", description="Leave the voice channel")
    async def leave(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            await interaction.response.send_message(
                "I'm not in a voice channel.", ephemeral=True
            )
            return

        player.cancel_idle_timer(interaction.guild.id)
        queues.get(interaction.guild.id).clear()
        await voice_client.disconnect()
        await status_panel.clear_panel(interaction.guild.id)
        await interaction.response.send_message("Disconnected.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceCog(bot))
