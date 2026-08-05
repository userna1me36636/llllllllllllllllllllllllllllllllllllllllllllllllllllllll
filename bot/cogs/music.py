from __future__ import annotations

import random
import subprocess

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import configured_owner
from bot.core.utils import DEFAULT_COLOR, embed, progress_bar, pulse_line
from bot.services.music import MusicManager, Track, ffmpeg_candidates
from bot.services.music_helpers import MusicHelperManager


class MusicSearchModal(discord.ui.Modal):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(title="Add Song")
        self.cog = cog
        self.guild_id = guild_id
        self.query = discord.ui.TextInput(label="Song, search, playlist, or URL", max_length=250)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.add_from_query(interaction, str(self.query))


class MusicControls(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Add Song", style=discord.ButtonStyle.success)
    async def add_song(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(MusicSearchModal(self.cog, self.guild_id))

    @discord.ui.button(label="Play", style=discord.ButtonStyle.primary)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.start_playback(interaction)

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

    @discord.ui.button(label="Song Info", style=discord.ButtonStyle.secondary)
    async def song_info(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        track = player.current or (list(player.queue._queue)[0] if not player.queue.empty() else None)
        if track is None:
            await interaction.response.send_message("No song loaded yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self.cog.song_info_embed(track), ephemeral=True)

    @discord.ui.button(label="Pulse", style=discord.ButtonStyle.primary)
    async def pulse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(embed=self.cog.pulse_embed(interaction.guild), ephemeral=True)
        await self.cog.refresh_panel(interaction.guild)

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
        self.playback_attempts: dict[int, int] = {}
        self.theme_colors: dict[int, int] = {}
        self.helpers = MusicHelperManager()
        self.bot.loop.create_task(self.helpers.start())

    async def cog_unload(self) -> None:
        await self.helpers.close()

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

    async def load_theme(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        color = settings.get("theme", {}).get("color")
        if color:
            self.theme_colors[guild.id] = int(color)
            colors = getattr(self.bot, "theme_colors", {})
            colors[guild.id] = int(color)
            setattr(self.bot, "theme_colors", colors)

    def theme_color(self, guild: discord.Guild | None) -> discord.Color:
        if guild is None:
            return DEFAULT_COLOR
        cached = self.theme_colors.get(guild.id) or getattr(self.bot, "theme_colors", {}).get(guild.id)
        return discord.Color(int(cached)) if cached else DEFAULT_COLOR

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
        description = f"{pulse_line()}\n\nAdd songs to the queue, then press Play to start them."
        e = embed("Music Panel", description, self.theme_color(guild))
        e.add_field(name="Status", value=state, inline=True)
        e.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        e.add_field(name="Loop", value="On" if player.loop_one else "Off", inline=True)
        if self.helpers.configured_count():
            e.add_field(name="Helper Bots", value=f"{len(self.helpers.ready_clients())}/{self.helpers.configured_count()} ready", inline=True)
        if current:
            e.add_field(name="Now Playing", value=f"[{current.title}]({current.webpage_url})", inline=False)
            if current.duration:
                e.add_field(name="Progress", value=progress_bar(0, current.duration), inline=False)
        else:
            e.add_field(name="Now Playing", value="Nothing yet. Use `/music add`, then `/music play`.", inline=False)
        queue_items = list(player.queue._queue)[:5]
        queue_text = "\n".join(f"`{i}.` {track.title[:80]}" for i, track in enumerate(queue_items, start=1))
        e.add_field(name="Up Next", value=queue_text or "Queue is empty.", inline=False)
        e.add_field(name="Interface Detail", value="Purple pulse controls are active. Press Pulse to refresh the style line.", inline=False)
        e.set_footer(text="AinBot music | clean purple interface")
        return e

    def song_info_embed(self, track: Track) -> discord.Embed:
        duration = "Unknown"
        if track.duration:
            minutes, seconds = divmod(int(track.duration), 60)
            hours, minutes = divmod(minutes, 60)
            duration = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
        e = embed("Song Info", f"{pulse_line()}\n\n[{track.title}]({track.webpage_url})")
        e.add_field(name="Artist / Channel", value=track.uploader or "Unknown", inline=True)
        e.add_field(name="Duration", value=duration, inline=True)
        e.add_field(name="Views", value=f"{track.view_count:,}" if track.view_count else "Unknown", inline=True)
        e.add_field(name="Requested By", value=f"<@{track.requester_id}>", inline=True)
        if track.local_path:
            e.add_field(name="Playback Mode", value="Temp download fallback", inline=True)
        if track.thumbnail:
            e.set_thumbnail(url=track.thumbnail)
        return e

    def pulse_embed(self, guild: discord.Guild | None) -> discord.Embed:
        e = embed("Purple Pulse", pulse_line(), self.theme_color(guild))
        e.add_field(name="Glow", value="Music panel refreshed with the server theme.", inline=False)
        return e

    async def send_or_update_panel(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        await self.load_theme(guild)
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
        await self.load_theme(guild)
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

    async def start_track(self, guild: discord.Guild, channel: discord.abc.Messageable, track: Track) -> None:
        player = self.manager.get(guild)
        vc = guild.voice_client
        if vc is None:
            return
        attempt = self.playback_attempts.get(guild.id, 0)

        async def report_after_error(error: Exception) -> None:
            try:
                await channel.send(embed=embed("Playback Error", f"`{type(error).__name__}`: {str(error)[:300]}"))
            except discord.HTTPException:
                pass

        async def retry_or_continue(error: Exception) -> None:
            attempt_now = self.playback_attempts.get(guild.id, 0)
            if attempt_now < 3:
                self.playback_attempts[guild.id] = attempt_now + 1
                try:
                    if attempt_now + 1 == 3 and not track.local_path:
                        await channel.send(embed=embed("Music Retry", f"Stream playback failed. Downloading `{track.title[:120]}` to temp audio and trying one last time."))
                        await player.download_track(track)
                    else:
                        await channel.send(embed=embed("Music Retry", f"FFmpeg crashed, retrying `{track.title[:120]}` with backup mode `{attempt_now + 2}/4`."))
                except discord.HTTPException:
                    pass
                except Exception as download_error:
                    self.playback_attempts[guild.id] = 0
                    await report_after_error(download_error)
                    await self.play_next(guild, channel)
                    return
                await self.start_track(guild, channel, track)
                return
            self.playback_attempts[guild.id] = 0
            await report_after_error(error)
            await self.play_next(guild, channel)

        def after(error: Exception | None) -> None:
            if error:
                self.bot.loop.create_task(retry_or_continue(error))
            else:
                self.playback_attempts[guild.id] = 0
                self.bot.loop.create_task(self.play_next(guild, channel))

        try:
            vc.play(player.source(track, attempt), after=after)
        except Exception as exc:
            await retry_or_continue(exc)
            return
        await self.send_or_update_panel(guild, channel)

    async def play_next(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        player = self.manager.get(guild)
        vc = guild.voice_client
        if vc is None:
            return
        self.playback_attempts[guild.id] = 0
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
        await self.start_track(guild, channel, track)

    async def add_from_query(self, interaction: discord.Interaction, query: str) -> None:
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
        await self.send_or_update_panel(interaction.guild, interaction.channel)

    async def start_playback(self, interaction: discord.Interaction) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        player = self.manager.get(interaction.guild)
        if vc.is_playing() or vc.is_paused():
            await interaction.response.send_message("Music is already started.", ephemeral=True)
            await self.refresh_panel(interaction.guild)
            return
        if player.queue.empty():
            await interaction.response.send_message("Queue is empty. Use `/music add` first.", ephemeral=True)
            await self.send_or_update_panel(interaction.guild, interaction.channel)
            return
        await interaction.response.send_message("Starting the queue.", ephemeral=True)
        await self.play_next(interaction.guild, interaction.channel)

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

    @music.command(name="add", description="Add a song or playlist to the queue")
    async def add(self, interaction: discord.Interaction, query: str) -> None:
        await self.add_from_query(interaction, query)

    @commands.command(name="addsong", aliases=["addtrack"])
    async def prefix_add_song(self, ctx: commands.Context, *, query: str) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Join a voice channel first.", mention_author=False)
            return
        if ctx.guild.voice_client is None:
            await ctx.author.voice.channel.connect(self_deaf=True)
        player = self.manager.get(ctx.guild)
        try:
            tracks = await player.resolve(query, ctx.author.id)
        except Exception as exc:
            await ctx.reply(embed=embed("Search Error", f"I could not load that track.\n`{type(exc).__name__}`: {str(exc)[:300]}"), mention_author=False)
            return
        for track in tracks[:50]:
            await player.queue.put(track)
        await self.send_or_update_panel(ctx.guild, ctx.channel)
        await ctx.reply(embed=embed("Queued", f"Added {len(tracks[:50])} track(s)."), mention_author=False)

    @music.command(name="play", description="Start playing the queued songs")
    async def play(self, interaction: discord.Interaction) -> None:
        await self.start_playback(interaction)

    @commands.command(name="play")
    async def prefix_play(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Join a voice channel first.", mention_author=False)
            return
        if ctx.guild.voice_client is None:
            await ctx.author.voice.channel.connect(self_deaf=True)
        player = self.manager.get(ctx.guild)
        vc = ctx.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            await ctx.reply("Music is already started.", mention_author=False)
            return
        if player.queue.empty():
            await ctx.reply("Queue is empty. Use `!addsong song name` first.", mention_author=False)
            await self.send_or_update_panel(ctx.guild, ctx.channel)
            return
        await ctx.reply("Starting the queue.", delete_after=5, mention_author=False)
        await self.play_next(ctx.guild, ctx.channel)

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

    @music.command(name="info", description="Show details about the current or next song")
    async def info(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        track = player.current or (list(player.queue._queue)[0] if not player.queue.empty() else None)
        if track is None:
            await interaction.response.send_message("No song loaded yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self.song_info_embed(track), ephemeral=True)

    @commands.command(name="songinfo", aliases=["sinfo", "trackinfo"])
    async def prefix_song_info(self, ctx: commands.Context) -> None:
        player = self.manager.get(ctx.guild)
        track = player.current or (list(player.queue._queue)[0] if not player.queue.empty() else None)
        if track is None:
            await ctx.reply("No song loaded yet.", mention_author=False)
            return
        await ctx.reply(embed=self.song_info_embed(track), mention_author=False)

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
        if interaction.guild.voice_client and interaction.guild.voice_client.source and hasattr(interaction.guild.voice_client.source, "volume"):
            interaction.guild.voice_client.source.volume = player.volume
        await interaction.response.send_message(f"Volume set to {percent}%.", ephemeral=True)
        await self.refresh_panel(interaction.guild)

    @music.command(name="doctor", description="Check music playback requirements")
    async def doctor(self, interaction: discord.Interaction) -> None:
        candidates = ffmpeg_candidates()
        lines = []
        for index, candidate in enumerate(candidates[:3], start=1):
            try:
                result = subprocess.run([candidate, "-version"], capture_output=True, text=True, timeout=8)
                first_line = (result.stdout or result.stderr or "No version output").splitlines()[0]
                lines.append(f"`{index}.` `{candidate}`\n{first_line[:180]}")
            except Exception as exc:
                lines.append(f"`{index}.` `{candidate}`\nFailed: `{type(exc).__name__}: {str(exc)[:120]}`")
        if not lines:
            lines.append("No FFmpeg candidates found.")
        try:
            deno = subprocess.run(["deno", "--version"], capture_output=True, text=True, timeout=8)
            deno_text = (deno.stdout or deno.stderr or "No Deno output").splitlines()[0]
        except Exception as exc:
            deno_text = f"Missing or failed: {type(exc).__name__}: {str(exc)[:120]}"
        lines.append(f"**Deno**\n`{deno_text[:180]}`")
        await interaction.response.send_message(embed=embed("Music Doctor", "\n\n".join(lines)), ephemeral=True)

    async def can_manage_helpers(self, user: discord.abc.User | None) -> bool:
        if await configured_owner(self.bot, user):
            return True
        return isinstance(user, discord.Member) and (user.guild_permissions.administrator or user.guild_permissions.move_members)

    @music.command(name="helpers", description="Show the extra music helper bots")
    async def helpers_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        rows = self.helpers.status(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                embed=embed("Music Helpers", "No helper bots are set yet. Add up to 10 extra bot tokens in `MUSIC_HELPER_TOKENS`."),
                ephemeral=True,
            )
            return
        lines = []
        for index, row in enumerate(rows, start=1):
            state = "ready" if row.ready else "starting"
            server = "in server" if row.in_server else "not invited"
            voice = row.connected_channel or "not in voice"
            lines.append(f"`{index}.` **{row.name}** - {state}, {server}, {voice}")
        await interaction.response.send_message(embed=embed("Music Helpers", "\n".join(lines)), ephemeral=True)

    @music.command(name="helpers_join", description="Make up to 10 helper bots join your voice channel")
    async def helpers_join(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 10] = 10) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.can_manage_helpers(interaction.user):
            await interaction.response.send_message("You need Move Members, Admin, or OWNER_IDS to use helper bots.", ephemeral=True)
            return
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("Join the voice channel first.", ephemeral=True)
            return
        if self.helpers.configured_count() == 0:
            await interaction.response.send_message("No helper bot tokens are set in `MUSIC_HELPER_TOKENS` yet.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        joined, errors = await self.helpers.summon(interaction.guild.id, interaction.user.voice.channel.id, count)
        text = f"{joined} helper bot(s) joined or moved to `{interaction.user.voice.channel.name}`."
        if errors:
            text += "\n\n" + "\n".join(errors)
        await interaction.followup.send(embed=embed("Music Helpers Joined", text), ephemeral=True)

    @music.command(name="helpers_leave", description="Disconnect the helper music bots")
    async def helpers_leave(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.can_manage_helpers(interaction.user):
            await interaction.response.send_message("You need Move Members, Admin, or OWNER_IDS to use helper bots.", ephemeral=True)
            return
        left = await self.helpers.release(interaction.guild.id)
        await interaction.response.send_message(embed=embed("Music Helpers Left", f"Disconnected {left} helper bot(s)."), ephemeral=True)

    @commands.group(name="musicbots", aliases=["helpers", "mbots"], invoke_without_command=True)
    async def prefix_musicbots(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        rows = self.helpers.status(ctx.guild.id)
        if not rows:
            await ctx.reply("No helper bots are set yet. Add up to 10 tokens in `MUSIC_HELPER_TOKENS`.", mention_author=False)
            return
        lines = []
        for index, row in enumerate(rows, start=1):
            state = "ready" if row.ready else "starting"
            server = "in server" if row.in_server else "not invited"
            voice = row.connected_channel or "not in voice"
            lines.append(f"`{index}.` **{row.name}** - {state}, {server}, {voice}")
        await ctx.reply(embed=embed("Music Helpers", "\n".join(lines)), mention_author=False)

    @prefix_musicbots.command(name="join")
    async def prefix_musicbots_join(self, ctx: commands.Context, count: int = 10) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not await self.can_manage_helpers(ctx.author):
            await ctx.reply("You need Move Members, Admin, or OWNER_IDS to use helper bots.", mention_author=False)
            return
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.reply("Join the voice channel first.", mention_author=False)
            return
        if self.helpers.configured_count() == 0:
            await ctx.reply("No helper bot tokens are set in `MUSIC_HELPER_TOKENS` yet.", mention_author=False)
            return
        joined, errors = await self.helpers.summon(ctx.guild.id, ctx.author.voice.channel.id, max(1, min(count, 10)))
        text = f"{joined} helper bot(s) joined or moved to `{ctx.author.voice.channel.name}`."
        if errors:
            text += "\n\n" + "\n".join(errors)
        await ctx.reply(embed=embed("Music Helpers Joined", text), mention_author=False)

    @prefix_musicbots.command(name="leave")
    async def prefix_musicbots_leave(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        if not await self.can_manage_helpers(ctx.author):
            await ctx.reply("You need Move Members, Admin, or OWNER_IDS to use helper bots.", mention_author=False)
            return
        left = await self.helpers.release(ctx.guild.id)
        await ctx.reply(embed=embed("Music Helpers Left", f"Disconnected {left} helper bot(s)."), mention_author=False)

    @music.command(name="lyrics", description="Show lyrics search guidance")
    async def lyrics(self, interaction: discord.Interaction, song: str | None = None) -> None:
        player = self.manager.get(interaction.guild)
        query = song or (player.current.title if player.current else "")
        await interaction.response.send_message(f"Lyrics search: https://genius.com/search?q={discord.utils.escape_markdown(query)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
