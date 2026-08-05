from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.utils import embed, progress_bar
from bot.services.music import MusicManager, Track


class MusicSearchModal(discord.ui.Modal):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(title="Play Music")
        self.cog = cog
        self.guild_id = guild_id
        self.query = discord.ui.TextInput(label="Song, search, playlist, or URL", max_length=250)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.play_from_query(interaction, str(self.query))


class MusicControls(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Play", style=discord.ButtonStyle.success)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(MusicSearchModal(self.cog, self.guild_id))

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Paused.", ephemeral=True)
        elif vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
        await self.cog.refresh_panel(interaction.guild)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        previous = self.cog.previous_tracks.get(interaction.guild_id)
        vc = interaction.guild.voice_client if interaction.guild else None
        if previous is None or vc is None:
            await interaction.response.send_message("No previous song yet.", ephemeral=True)
            return
        if player.current:
            await player.queue.put(player.current)
        player.current = previous
        vc.stop()
        await interaction.response.send_message("Going back to the previous song.", ephemeral=True)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc:
            vc.stop()
            await interaction.response.send_message("Skipped.", ephemeral=True)
        else:
            await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        player.loop_one = not player.loop_one
        await interaction.response.send_message(f"Loop current: `{player.loop_one}`", ephemeral=True)
        await self.cog.refresh_panel(interaction.guild)

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary)
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        items = list(player.queue._queue)[:10]
        e = embed("Music Queue", f"Current: `{player.current.title if player.current else 'Nothing'}`")
        if not items:
            e.add_field(name="Up Next", value="Queue is empty.", inline=False)
        for i, track in enumerate(items, start=1):
            e.add_field(name=str(i), value=track.title[:250], inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        while not player.queue.empty():
            player.queue.get_nowait()
        player.current = None
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc:
            await vc.disconnect()
        await self.cog.clear_panel(interaction.guild)
        await interaction.response.send_message("Left the voice channel.", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.manager = MusicManager()
        self.panel_messages: dict[int, discord.Message] = {}
        self.panel_channels: dict[int, int] = {}
        self.previous_tracks: dict[int, Track] = {}

    music = app_commands.Group(name="music", description="Music playback")

    async def ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return None
        if interaction.guild.voice_client:
            return interaction.guild.voice_client
        vc = await member.voice.channel.connect(self_deaf=True)
        await self.send_or_update_panel(interaction.guild, interaction.channel)
        return vc

    def panel_embed(self, guild: discord.Guild) -> discord.Embed:
        player = self.manager.get(guild)
        vc = guild.voice_client
        current = player.current
        state = "Disconnected"
        if vc and vc.is_playing():
            state = "Playing"
        elif vc and vc.is_paused():
            state = "Paused"
        elif vc:
            state = "Connected"
        description = "Use the buttons below to control music while I am in VC."
        e = embed("Music Panel", description)
        e.add_field(name="Status", value=state, inline=True)
        e.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        e.add_field(name="Loop", value="On" if player.loop_one else "Off", inline=True)
        if current:
            e.add_field(name="Now Playing", value=f"[{current.title}]({current.webpage_url})", inline=False)
            if current.duration:
                e.add_field(name="Progress", value=progress_bar(0, current.duration), inline=False)
        else:
            e.add_field(name="Now Playing", value="Nothing yet. Press Play or use `/music play`.", inline=False)
        queue_items = list(player.queue._queue)[:5]
        queue_text = "\n".join(f"`{i}.` {track.title[:80]}" for i, track in enumerate(queue_items, start=1))
        e.add_field(name="Up Next", value=queue_text or "Queue is empty.", inline=False)
        e.set_footer(text="Panel updates when songs change or buttons are used.")
        return e

    async def send_or_update_panel(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        view = MusicControls(self, guild.id)
        old = self.panel_messages.get(guild.id)
        if old:
            try:
                await old.edit(embed=self.panel_embed(guild), view=view)
                return
            except discord.HTTPException:
                self.panel_messages.pop(guild.id, None)
        try:
            message = await channel.send(embed=self.panel_embed(guild), view=view)
            self.panel_messages[guild.id] = message
            self.panel_channels[guild.id] = message.channel.id
        except discord.HTTPException:
            pass

    async def refresh_panel(self, guild: discord.Guild | None) -> None:
        if guild is None:
            return
        message = self.panel_messages.get(guild.id)
        if message is None:
            return
        try:
            await message.edit(embed=self.panel_embed(guild), view=MusicControls(self, guild.id))
        except discord.HTTPException:
            self.panel_messages.pop(guild.id, None)

    async def clear_panel(self, guild: discord.Guild | None) -> None:
        if guild is None:
            return
        message = self.panel_messages.pop(guild.id, None)
        self.panel_channels.pop(guild.id, None)
        if message:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    async def play_next(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        player = self.manager.get(guild)
        vc = guild.voice_client
        if vc is None:
            return
        if player.loop_one and player.current:
            track = player.current
        else:
            if player.current:
                self.previous_tracks[guild.id] = player.current
                if player.loop_queue:
                    await player.queue.put(player.current)
            if player.queue.empty():
                player.current = None
                await self.refresh_panel(guild)
                return
            track = await player.queue.get()
            player.current = track

        async def report_after_error(error: Exception) -> None:
            try:
                await channel.send(embed=embed("Playback Error", f"`{type(error).__name__}`: {str(error)[:300]}"))
            except discord.HTTPException:
                pass

        def after(error: Exception | None) -> None:
            if error:
                self.bot.loop.create_task(report_after_error(error))
            self.bot.loop.create_task(self.play_next(guild, channel))

        try:
            vc.play(player.source(track), after=after)
        except Exception as exc:
            player.current = None
            try:
                await channel.send(embed=embed("Playback Error", f"I queued the track, but could not start audio.\n`{type(exc).__name__}`: {str(exc)[:300]}"))
            except discord.HTTPException:
                pass
            await self.refresh_panel(guild)
            return
        await self.send_or_update_panel(guild, channel)

    async def play_from_query(self, interaction: discord.Interaction, query: str) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        player = self.manager.get(interaction.guild)
        try:
            tracks = await player.resolve(query, interaction.user.id)
        except Exception as exc:
            await interaction.followup.send(embed=embed("Search Error", f"I could not load that track.\n`{type(exc).__name__}`: {str(exc)[:300]}"), ephemeral=True)
            return
        if not tracks:
            await interaction.followup.send("I could not find any tracks for that.", ephemeral=True)
            return
        for track in tracks[:50]:
            await player.queue.put(track)
        await interaction.followup.send(embed=embed("Queued", f"Added {len(tracks[:50])} track(s)."), ephemeral=True)
        if not vc.is_playing() and not vc.is_paused():
            await self.play_next(interaction.guild, interaction.channel)
        else:
            await self.send_or_update_panel(interaction.guild, interaction.channel)

    @music.command(name="join", description="Join your voice channel and send the music panel")
    async def join(self, interaction: discord.Interaction) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        if not interaction.response.is_done():
            await interaction.response.send_message("Joined and sent the music panel.", ephemeral=True)

    @music.command(name="panel", description="Send or refresh the music control panel")
    async def panel(self, interaction: discord.Interaction) -> None:
        if interaction.guild.voice_client is None:
            vc = await self.ensure_voice(interaction)
            if vc is None:
                return
        await self.send_or_update_panel(interaction.guild, interaction.channel)
        if not interaction.response.is_done():
            await interaction.response.send_message("Music panel sent.", ephemeral=True)

    @commands.command(name="musicpanel", aliases=["mpanel"])
    async def prefix_music_panel(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Join a voice channel first.", mention_author=False)
            return
        if ctx.guild.voice_client is None:
            await ctx.author.voice.channel.connect(self_deaf=True)
        await self.send_or_update_panel(ctx.guild, ctx.channel)
        await ctx.reply("Music panel sent.", delete_after=5, mention_author=False)

    @commands.command(name="join")
    async def prefix_join(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Join a voice channel first.", mention_author=False)
            return
        if ctx.guild.voice_client is None:
            await ctx.author.voice.channel.connect(self_deaf=True)
        await self.send_or_update_panel(ctx.guild, ctx.channel)
        await ctx.reply("Joined and sent the music panel.", delete_after=5, mention_author=False)

    @music.command(name="play", description="Play a song or playlist")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await self.play_from_query(interaction, query)

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
        await interaction.response.send_message(embed=self.panel_embed(interaction.guild), view=MusicControls(self, interaction.guild_id))

    @music.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.pause()
        await interaction.response.send_message("Paused.", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.resume()
        await interaction.response.send_message("Resumed.", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.send_message("Skipped.", ephemeral=True)

    @music.command(name="back", description="Play the previous song again")
    async def back(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        previous = self.previous_tracks.get(interaction.guild_id)
        vc = interaction.guild.voice_client
        if previous is None or vc is None:
            await interaction.response.send_message("No previous song yet.", ephemeral=True)
            return
        if player.current:
            await player.queue.put(player.current)
        player.current = previous
        vc.stop()
        await interaction.response.send_message("Going back to the previous song.", ephemeral=True)

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
        await self.refresh_panel(interaction.guild)

    @music.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        while not player.queue.empty():
            player.queue.get_nowait()
        player.current = None
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await self.clear_panel(interaction.guild)
        await interaction.response.send_message("Stopped.", ephemeral=True)

    @music.command(name="loop", description="Toggle current-track looping")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_one = not player.loop_one
        await interaction.response.send_message(f"Loop current: `{player.loop_one}`", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="loop_queue", description="Toggle queue looping")
    async def loop_queue(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_queue = not player.loop_queue
        await interaction.response.send_message(f"Loop queue: `{player.loop_queue}`", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        items = list(player.queue._queue)
        random.shuffle(items)
        player.queue._queue.clear()
        for item in items:
            player.queue._queue.append(item)
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="volume", description="Set playback volume")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 1, 200]) -> None:
        player = self.manager.get(interaction.guild)
        player.volume = percent / 100
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = player.volume
        await interaction.response.send_message(f"Volume set to {percent}%.", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="lyrics", description="Show lyrics search guidance")
    async def lyrics(self, interaction: discord.Interaction, song: str | None = None) -> None:
        player = self.manager.get(interaction.guild)
        query = song or (player.current.title if player.current else "")
        await interaction.response.send_message(f"Lyrics search: https://genius.com/search?q={discord.utils.escape_markdown(query)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
