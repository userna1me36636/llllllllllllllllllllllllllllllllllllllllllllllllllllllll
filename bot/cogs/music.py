from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.utils import embed, progress_bar
from bot.services.music import MusicManager, Track


class MusicControls(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
        await interaction.response.defer()

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.secondary)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
        await interaction.response.defer()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.defer()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.manager = MusicManager()

    music = app_commands.Group(name="music", description="Music playback")

    async def ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return None
        if interaction.guild.voice_client:
            return interaction.guild.voice_client
        return await member.voice.channel.connect(self_deaf=True)

    async def play_next(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        player = self.manager.get(guild)
        vc = guild.voice_client
        if vc is None:
            return
        if player.loop_one and player.current:
            track = player.current
        else:
            if player.current and player.loop_queue:
                await player.queue.put(player.current)
            if player.queue.empty():
                player.current = None
                return
            track = await player.queue.get()
            player.current = track
        def after(error: Exception | None) -> None:
            self.bot.loop.create_task(self.play_next(guild, channel))
        vc.play(player.source(track), after=after)
        e = embed("Now Playing", f"[{track.title}]({track.webpage_url})\n{progress_bar(0, track.duration or 1)}")
        await channel.send(embed=e, view=MusicControls(self, guild.id))

    @music.command(name="play", description="Play a song or playlist")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        await interaction.response.defer()
        player = self.manager.get(interaction.guild)
        tracks = await player.resolve(query, interaction.user.id)
        for track in tracks[:50]:
            await player.queue.put(track)
        await interaction.followup.send(embed=embed("Queued", f"Added {len(tracks[:50])} track(s)."))
        if not vc.is_playing() and not vc.is_paused():
            await self.play_next(interaction.guild, interaction.channel)

    @music.command(name="queue", description="Show the queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        items = list(player.queue._queue)[:15]
        e = embed("Queue", f"Current: {player.current.title if player.current else 'Nothing'}")
        for i, track in enumerate(items, start=1):
            e.add_field(name=str(i), value=track.title, inline=False)
        await interaction.response.send_message(embed=e)

    @music.command(name="nowplaying", description="Show the current song")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        if player.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed("Now Playing", f"[{player.current.title}]({player.current.webpage_url})"))

    @music.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.pause()
        await interaction.response.send_message("Paused.", ephemeral=True)

    @music.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.resume()
        await interaction.response.send_message("Resumed.", ephemeral=True)

    @music.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @music.command(name="back", description="Play the previous song again")
    async def back(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Back is tracked after playback history is available. Use `/music play` to replay a title from history.", ephemeral=True)

    @music.command(name="remove", description="Remove a queued song by number")
    async def remove(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 100]) -> None:
        player = self.manager.get(interaction.guild)
        items = list(player.queue._queue)
        if number > len(items):
            await interaction.response.send_message("That queue number does not exist.", ephemeral=True)
            return
        removed = items.pop(number - 1)
        player.queue._queue.clear()
        for item in items:
            player.queue._queue.append(item)
        await interaction.response.send_message(f"Removed `{removed.title}`.", ephemeral=True)

    @music.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        while not player.queue.empty():
            player.queue.get_nowait()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Stopped.", ephemeral=True)

    @music.command(name="loop", description="Toggle current-track looping")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_one = not player.loop_one
        await interaction.response.send_message(f"Loop current: `{player.loop_one}`", ephemeral=True)

    @music.command(name="loop_queue", description="Toggle queue looping")
    async def loop_queue(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_queue = not player.loop_queue
        await interaction.response.send_message(f"Loop queue: `{player.loop_queue}`", ephemeral=True)

    @music.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        items = list(player.queue._queue)
        random.shuffle(items)
        player.queue._queue.clear()
        for item in items:
            player.queue._queue.append(item)
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)

    @music.command(name="volume", description="Set playback volume")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 1, 200]) -> None:
        player = self.manager.get(interaction.guild)
        player.volume = percent / 100
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = player.volume
        await interaction.response.send_message(f"Volume set to {percent}%.", ephemeral=True)

    @music.command(name="lyrics", description="Show lyrics search guidance")
    async def lyrics(self, interaction: discord.Interaction, song: str | None = None) -> None:
        player = self.manager.get(interaction.guild)
        query = song or (player.current.title if player.current else "")
        await interaction.response.send_message(f"Lyrics search: https://genius.com/search?q={discord.utils.escape_markdown(query)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
