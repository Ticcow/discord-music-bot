import discord
from discord import app_commands
from discord.ext import commands

from bot.music import player
from bot.music.player import ensure_voice_client
from bot.music.queue import queues
from bot.music.youtube import search

_NOT_AUTHORIZED_MESSAGE = "You need to be in the bot's voice channel to do that."


async def _check_authorized(interaction: discord.Interaction, *, deferred: bool) -> bool:
    if player.is_authorized(interaction.guild.voice_client, interaction.user):
        return True
    if deferred:
        await interaction.followup.send(_NOT_AUTHORIZED_MESSAGE, ephemeral=True)
    else:
        await interaction.response.send_message(_NOT_AUTHORIZED_MESSAGE, ephemeral=True)
    return False


class PlaybackCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="play", description="Search YouTube and play/queue a track")
    @app_commands.describe(query="Song name, artist, or YouTube search terms")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()

        if not await _check_authorized(interaction, deferred=True):
            return

        voice_client = await ensure_voice_client(interaction)
        if voice_client is None:
            return

        try:
            track = await search(query, requested_by=interaction.user.display_name)
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return

        await player.enqueue_priority(voice_client, track)
        await interaction.followup.send(f"Queued **{track.title}** - up next.")

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        if not await _check_authorized(interaction, deferred=False):
            return
        voice_client = interaction.guild.voice_client
        if voice_client is not None and await player.pause(voice_client):
            await interaction.response.send_message("Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        if not await _check_authorized(interaction, deferred=False):
            return
        voice_client = interaction.guild.voice_client
        if voice_client is not None and await player.resume(voice_client):
            await interaction.response.send_message("Resumed.")
        else:
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        if not await _check_authorized(interaction, deferred=False):
            return
        voice_client = interaction.guild.voice_client
        if voice_client and player.skip(voice_client):
            await interaction.response.send_message("Skipped.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @app_commands.command(name="queue", description="Show the upcoming queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        guild_queue = queues.get(interaction.guild.id)
        lines = []
        if guild_queue.now_playing:
            lines.append(f"Now playing: **{guild_queue.now_playing.title}**")
        upcoming = guild_queue.peek_all()
        if upcoming:
            lines.append("Up next:")
            lines.extend(f"{i+1}. {t.title}" for i, t in enumerate(upcoming))
        if not lines:
            lines.append("The queue is empty.")
        await interaction.response.send_message("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PlaybackCog(bot))
