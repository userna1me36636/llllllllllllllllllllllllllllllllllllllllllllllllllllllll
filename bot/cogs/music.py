from __future__ import annotations

import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.utils import embed, progress_bar
from bot.services.music import MusicManager, Track


class MusicControls(discord.ui.View):
    def __init__(self, cog: "Music", guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Pause/Resume", style=discord.ButtonStyle.secondary, custom_id="music:pause_resume")
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
        elif vc and vc.is_paused():
            vc.resume()
        await self.cog.update_panel(interaction.guild)
        await interaction.response.defer()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, custom_id="music:back")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.play_previous(interaction.guild, interaction.channel)
        await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="music:next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, custom_id="music:loop")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        player.loop_one = not player.loop_one
        await self.cog.update_panel(interaction.guild)
        await interaction.response.defer()

    @discord.ui.button(label="Playlist Loop", style=discord.ButtonStyle.secondary, custom_id="music:loop_playlist")
    async def loop_playlist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        player.loop_queue = not player.loop_queue
        await self.cog.update_panel(interaction.guild)
        await interaction.response.defer()

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, custom_id="music:leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.cog.manager.get(interaction.guild)
        while not player.queue.empty():
            player.queue.get_nowait()
        player.current = None
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await self.cog.mark_panel_disconnected(interaction.guild)
        await interaction.response.defer()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.manager = MusicManager()
        bot.add_view(MusicControls(self, 0))

    music = app_commands.Group(name="music", description="Music playback")

    async def ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return None
        if interaction.guild.voice_client:
            return interaction.guild.voice_client
        return await member.voice.channel.connect(self_deaf=True)

    def panel_embed(self, guild: discord.Guild) -> discord.Embed:
        player = self.manager.get(guild)
        vc = guild.voice_client
        status = "Disconnected"
        if vc and vc.is_paused():
            status = "Paused"
        elif vc and vc.is_playing():
            status = "Playing"
        elif vc:
            status = "Connected"
        current = player.current
        e = embed("Music Player", f"Status: `{status}`")
        if current:
            e.add_field(name="Now Playing", value=f"[{current.title}]({current.webpage_url})\nRequested by <@{current.requester_id}>", inline=False)
        else:
            e.add_field(name="Now Playing", value="Nothing is playing.", inline=False)
        queue_items = list(player.queue._queue)[:10]
        queue_text = "\n".join(f"`{i}.` {track.title}" for i, track in enumerate(queue_items, start=1))
        e.add_field(name=f"Queue ({player.queue.qsize()})", value=queue_text or "Queue is empty.", inline=False)
        e.add_field(name="Modes", value=f"Loop song: `{player.loop_one}`\nLoop playlist: `{player.loop_queue}`\nVolume: `{round(player.volume * 100)}%`", inline=True)
        e.add_field(name="Commands", value="`/music play`\n`/music play_next`\n`/music remove`\n`/music queue`", inline=True)
        e.set_footer(text="This panel updates while the bot is in voice.")
        return e

    async def update_panel(self, guild: discord.Guild, channel: discord.abc.Messageable | None = None) -> discord.Message | None:
        player = self.manager.get(guild)
        target_channel = channel
        channel_id = getattr(target_channel, "id", None) or player.panel_channel_id
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)) and channel_id:
            target_channel = guild.get_channel(channel_id)
            if target_channel is None:
                try:
                    fetched = await self.bot.fetch_channel(channel_id)
                    if getattr(fetched, "guild", None) == guild:
                        target_channel = fetched
                except discord.HTTPException:
                    target_channel = None
        if target_channel is None and player.panel_channel_id:
            target_channel = guild.get_channel(player.panel_channel_id)
        if not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            return None
        view = MusicControls(self, guild.id)
        if player.panel_message_id:
            try:
                message = await target_channel.fetch_message(player.panel_message_id)
                await message.edit(embed=self.panel_embed(guild), view=view)
                return message
            except discord.HTTPException:
                player.panel_message_id = None
        try:
            message = await target_channel.send(embed=self.panel_embed(guild), view=view)
        except discord.HTTPException:
            return None
        player.panel_channel_id = target_channel.id
        player.panel_message_id = message.id
        return message

    async def mark_panel_disconnected(self, guild: discord.Guild) -> None:
        player = self.manager.get(guild)
        if not player.panel_channel_id or not player.panel_message_id:
            return
        channel = guild.get_channel(player.panel_channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            player.panel_message_id = None
            return
        try:
            message = await channel.fetch_message(player.panel_message_id)
            await message.edit(embed=self.panel_embed(guild), view=MusicControls(self, guild.id))
        except discord.HTTPException:
            pass

    async def join_voice_from_member(self, member: discord.Member) -> discord.VoiceClient | None:
        if member.voice is None or member.voice.channel is None:
            return None
        vc = member.guild.voice_client
        if vc and vc.channel != member.voice.channel:
            await vc.move_to(member.voice.channel)
            return vc
        if vc:
            return vc
        return await member.voice.channel.connect(self_deaf=True)

    async def play_previous(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        player = self.manager.get(guild)
        if player.previous is None:
            return
        if player.current:
            player.queue._queue.appendleft(player.current)
        player.queue._queue.appendleft(player.previous)
        if guild.voice_client:
            guild.voice_client.stop()
        await self.update_panel(guild, channel)

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
                await self.update_panel(guild, channel)
                return
            track = await player.queue.get()
            if player.current:
                player.previous = player.current
                player.history.append(player.current)
                player.history = player.history[-25:]
            player.current = track
        def after(error: Exception | None) -> None:
            self.bot.loop.create_task(self.play_next(guild, channel))
        vc.play(player.source(track), after=after)
        await self.update_panel(guild, channel)

    @music.command(name="play", description="Play a song or playlist")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        await interaction.response.defer()
        player = self.manager.get(interaction.guild)
        player.panel_channel_id = interaction.channel_id
        tracks = await player.resolve(query, interaction.user.id)
        for track in tracks[:50]:
            await player.queue.put(track)
        await interaction.followup.send(embed=embed("Queued", f"Added {len(tracks[:50])} track(s)."))
        await self.update_panel(interaction.guild, interaction.channel)
        if not vc.is_playing() and not vc.is_paused():
            await self.play_next(interaction.guild, interaction.channel)

    @music.command(name="join", description="Join your voice channel and post the music panel")
    async def join(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this inside a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        vc = await self.join_voice_from_member(interaction.user)
        if vc is None:
            await interaction.followup.send("Join a voice channel first.", ephemeral=True)
            return
        player = self.manager.get(interaction.guild)
        player.panel_channel_id = interaction.channel_id
        await self.update_panel(interaction.guild, interaction.channel)
        await interaction.followup.send(f"Joined {vc.channel.mention} and posted the music panel.", ephemeral=True)

    @music.command(name="panel", description="Post or refresh the music interface")
    async def panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if isinstance(interaction.user, discord.Member):
            await self.join_voice_from_member(interaction.user)
        player = self.manager.get(interaction.guild)
        player.panel_channel_id = interaction.channel_id
        message = await self.update_panel(interaction.guild, interaction.channel)
        if message is None:
            await interaction.followup.send("I could not send the panel in this channel. Give me Send Messages and Embed Links.", ephemeral=True)
            return
        await interaction.followup.send("Music panel sent/refreshed.", ephemeral=True)

    @commands.command(name="join")
    async def join_prefix(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        vc = await self.join_voice_from_member(ctx.author)
        if vc is None:
            await ctx.reply("Join a voice channel first.", mention_author=False)
            return
        player = self.manager.get(ctx.guild)
        player.panel_channel_id = ctx.channel.id
        await self.update_panel(ctx.guild, ctx.channel)
        await ctx.reply(f"Joined {vc.channel.mention} and posted the music panel.", mention_author=False)

    @commands.command(name="musicpanel", aliases=["mpanel", "panal"])
    async def musicpanel_prefix(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        if isinstance(ctx.author, discord.Member):
            await self.join_voice_from_member(ctx.author)
        player = self.manager.get(ctx.guild)
        player.panel_channel_id = ctx.channel.id
        message = await self.update_panel(ctx.guild, ctx.channel)
        if message is None:
            await ctx.reply("I could not send the panel here. I need Send Messages and Embed Links.", mention_author=False)
            return
        await ctx.reply("Music panel sent/refreshed.", mention_author=False)

    @music.command(name="play_next", description="Put a song next in the queue")
    async def play_next_command(self, interaction: discord.Interaction, query: str) -> None:
        vc = await self.ensure_voice(interaction)
        if vc is None:
            return
        await interaction.response.defer()
        player = self.manager.get(interaction.guild)
        player.panel_channel_id = interaction.channel_id
        tracks = await player.resolve(query, interaction.user.id)
        for track in reversed(tracks[:10]):
            player.queue._queue.appendleft(track)
        await self.update_panel(interaction.guild, interaction.channel)
        await interaction.followup.send(embed=embed("Queued Next", f"Added {len(tracks[:10])} track(s) to the front."))
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
        await self.play_previous(interaction.guild, interaction.channel)
        await interaction.response.send_message("Trying previous track.", ephemeral=True)

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
        await self.update_panel(interaction.guild, interaction.channel)

    @music.command(name="stop", description="Stop and clear queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        while not player.queue.empty():
            player.queue.get_nowait()
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Stopped.", ephemeral=True)
        await self.mark_panel_disconnected(interaction.guild)

    @music.command(name="loop", description="Toggle current-track looping")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_one = not player.loop_one
        await interaction.response.send_message(f"Loop current: `{player.loop_one}`", ephemeral=True)
        await self.update_panel(interaction.guild, interaction.channel)

    @music.command(name="loop_queue", description="Toggle queue looping")
    async def loop_queue(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        player.loop_queue = not player.loop_queue
        await interaction.response.send_message(f"Loop queue: `{player.loop_queue}`", ephemeral=True)
        await self.update_panel(interaction.guild, interaction.channel)

    @music.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.manager.get(interaction.guild)
        items = list(player.queue._queue)
        random.shuffle(items)
        player.queue._queue.clear()
        for item in items:
            player.queue._queue.append(item)
        await interaction.response.send_message("Queue shuffled.", ephemeral=True)
        await self.update_panel(interaction.guild, interaction.channel)

    @music.command(name="volume", description="Set playback volume")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 1, 200]) -> None:
        player = self.manager.get(interaction.guild)
        player.volume = percent / 100
        if interaction.guild.voice_client and interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = player.volume
        await interaction.response.send_message(f"Volume set to {percent}%.", ephemeral=True)
        await self.update_panel(interaction.guild, interaction.channel)

    @music.command(name="lyrics", description="Show lyrics search guidance")
    async def lyrics(self, interaction: discord.Interaction, song: str | None = None) -> None:
        player = self.manager.get(interaction.guild)
        query = song or (player.current.title if player.current else "")
        await interaction.response.send_message(f"Lyrics search: https://genius.com/search?q={discord.utils.escape_markdown(query)}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if self.bot.user is None or member.id != self.bot.user.id:
            return
        if before.channel is not None and after.channel is None:
            await self.mark_panel_disconnected(member.guild)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
