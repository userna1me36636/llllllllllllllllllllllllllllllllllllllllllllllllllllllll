from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner
from bot.core.utils import embed, parse_color, pulse_line, style_embed


class VcMusicTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.vc_owners: dict[int, int] = {}
        self.vc_sessions: dict[tuple[int, int], dict[str, float | bool]] = {}

    vc = app_commands.Group(name="vc", description="Voice channel controls")
    theme = app_commands.Group(name="theme", description="Bot interface style")

    async def themed_embed(self, guild_id: int, title: str, description: str = "") -> discord.Embed:
        theme = await self.theme_data(guild_id)
        color = discord.Color(int(theme.get("color", 11146790)))
        e = discord.Embed(title=title, description=description or None, color=color)
        if description:
            style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        return e

    async def glass_response(self, interaction: discord.Interaction, title: str, description: str = "", *, ephemeral: bool = True) -> None:
        await interaction.response.send_message(embed=await self.themed_embed(interaction.guild_id, title, description), ephemeral=ephemeral)

    async def glass_reply(self, ctx: commands.Context, title: str, description: str = "") -> None:
        await ctx.reply(embed=await self.themed_embed(ctx.guild.id, title, description), mention_author=False)

    @app_commands.command(name="help", description="Show this bot's music and VC commands")
    async def help_command(self, interaction: discord.Interaction) -> None:
        e = await self.help_embed(interaction.guild_id)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.command(name="help")
    async def prefix_help_command(self, ctx: commands.Context) -> None:
        await ctx.reply(embed=await self.help_embed(ctx.guild.id), mention_author=False)

    async def help_embed(self, guild_id: int) -> discord.Embed:
        e = await self.themed_embed(guild_id, "VC + Music Commands", "This bot only runs music, join-to-create, voice controls, theme, and sync.")
        e.add_field(
            name="Music",
            value=(
                "`,join`\n`,musicpanel`\n`,addsong <song or link>`\n`,play`\n`,songinfo`\n"
                "`,musicbots`\n`,musicbots join 10`\n`,musicbots leave`"
            ),
            inline=False,
        )
        e.add_field(
            name="Voice",
            value=(
                "`,vc claim`\n`,vc lock`\n`,vc unlock`\n`,vc hide`\n`,vc reveal`\n`,vc rename <name>`\n"
                "`,vc limit <number>`\n`,vc permit @user`\n`,vc reject @user`\n`,vc transfer @user`\n"
                "`,drag old vc to new vc`\n`,dragall old vc to new vc`\n`,moveall old vc to new vc`"
            ),
            inline=False,
        )
        e.add_field(
            name="Theme",
            value="`,theme color glassred`\n`,theme banner <image-or-gif-link>`\n`,theme effects on`\n`,theme effects off`",
            inline=False,
        )
        e.add_field(
            name="Owner",
            value="`,ainrename <new bot name>`\n`,ainprof` with an attached image",
            inline=False,
        )
        return e

    @app_commands.command(name="sync", description="Owner only: refresh slash commands")
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await self.glass_response(interaction, "Owner Only", "Only users listed in `OWNER_IDS` can refresh commands.")
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        synced = await self.bot.tree.sync()
        guild_synced = []
        if interaction.guild is not None:
            self.bot.tree.copy_global_to(guild=interaction.guild)
            guild_synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(embed=await self.themed_embed(interaction.guild_id, "Sync Complete", f"`{len(synced)}` global and `{len(guild_synced)}` server commands refreshed."), ephemeral=True)

    async def save_theme_value(self, guild_id: int, key: str, value: object) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        theme[key] = value
        await self.bot.db.set_settings_value(guild_id, "theme", theme, self.bot.settings.default_prefix)
        if key == "color":
            colors = getattr(self.bot, "theme_colors", {})
            colors[guild_id] = int(value)
            setattr(self.bot, "theme_colors", colors)
        return theme

    async def theme_data(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("theme", {})

    @theme.command(name="color", description="Set the red glass interface color")
    @app_admin()
    async def theme_color(self, interaction: discord.Interaction, color: str = "glassred") -> None:
        try:
            parsed = parse_color(color)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        theme = await self.save_theme_value(interaction.guild_id, "color", parsed.value)
        e = embed("Theme Updated", f"{pulse_line()}\n\nInterface color set to `{color}`.", parsed)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="banner", description="Set an image/GIF banner for the music and VC panels")
    @app_admin()
    async def theme_banner(self, interaction: discord.Interaction, url: str | None = None) -> None:
        if url and not url.startswith(("http://", "https://")):
            await self.glass_response(interaction, "Bad Banner Link", "Use a direct image/GIF link that starts with `http` or `https`.")
            return
        theme = await self.save_theme_value(interaction.guild_id, "banner_url", url or "")
        color = discord.Color(int(theme.get("color", 11146790)))
        e = embed("Theme Banner Updated", "Panel banner cleared." if not url else "New panel banner saved.", color)
        style_embed(e, banner_url=url, flashy=theme.get("effects", True))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="effects", description="Turn glass effects on or off")
    @app_admin()
    async def theme_effects(self, interaction: discord.Interaction, enabled: bool = True) -> None:
        theme = await self.save_theme_value(interaction.guild_id, "effects", enabled)
        color = discord.Color(int(theme.get("color", 11146790)))
        e = embed("Theme Effects Updated", f"Glass effects are now **{'on' if enabled else 'off'}**.", color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=enabled)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="preview", description="Preview the current interface style")
    async def theme_preview(self, interaction: discord.Interaction) -> None:
        theme = await self.theme_data(interaction.guild_id)
        color = discord.Color(int(theme.get("color", 11146790)))
        e = embed("Theme Preview", pulse_line(), color)
        e.add_field(name="Effects", value="On" if theme.get("effects", True) else "Off", inline=True)
        e.add_field(name="Banner", value="Set" if theme.get("banner_url") else "Not set", inline=True)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.group(name="theme", invoke_without_command=True)
    async def theme_prefix(self, ctx: commands.Context) -> None:
        await self.glass_reply(ctx, "Theme Commands", "Use `theme color glassred`, `theme banner <link>`, or `theme effects on`.")

    @theme_prefix.command(name="color")
    async def theme_prefix_color(self, ctx: commands.Context, color: str = "glassred") -> None:
        if not ctx.author.guild_permissions.administrator and not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Administrator or OWNER_IDS only.", mention_author=False)
            return
        try:
            parsed = parse_color(color)
        except ValueError as exc:
            await self.glass_reply(ctx, "Bad Color", str(exc))
            return
        theme = await self.save_theme_value(ctx.guild.id, "color", parsed.value)
        e = embed("Theme Updated", f"{pulse_line()}\n\nInterface color set to `{color}`.", parsed)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        await ctx.reply(embed=e, mention_author=False)

    @theme_prefix.command(name="banner")
    async def theme_prefix_banner(self, ctx: commands.Context, url: str | None = None) -> None:
        if not ctx.author.guild_permissions.administrator and not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Administrator or OWNER_IDS only.", mention_author=False)
            return
        theme = await self.save_theme_value(ctx.guild.id, "banner_url", url or "")
        color = discord.Color(int(theme.get("color", 11146790)))
        e = embed("Theme Banner Updated", "Panel banner cleared." if not url else "New panel banner saved.", color)
        style_embed(e, banner_url=url, flashy=theme.get("effects", True))
        await ctx.reply(embed=e, mention_author=False)

    @theme_prefix.command(name="effects")
    async def theme_prefix_effects(self, ctx: commands.Context, enabled: str = "on") -> None:
        if not ctx.author.guild_permissions.administrator and not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Administrator or OWNER_IDS only.", mention_author=False)
            return
        state = enabled.lower() in {"on", "yes", "true", "1", "enable", "enabled"}
        theme = await self.save_theme_value(ctx.guild.id, "effects", state)
        color = discord.Color(int(theme.get("color", 11146790)))
        e = embed("Theme Effects Updated", f"Glass effects are now **{'on' if state else 'off'}**.", color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=state)
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="ainrename", hidden=True)
    async def ainrename_prefix(self, ctx: commands.Context, *, name: str) -> None:
        if not await configured_owner(self.bot, ctx.author):
            await self.glass_reply(ctx, "Owner Only", "Only users listed in `OWNER_IDS` can rename the bot.")
            return
        try:
            await self.bot.user.edit(username=name.strip()[:32])
        except discord.HTTPException as exc:
            await self.glass_reply(ctx, "Profile Error", f"I could not rename the bot: `{type(exc).__name__}`")
            return
        await self.glass_reply(ctx, "Profile Updated", f"Bot name changed to **{name.strip()[:32]}**.")

    @commands.command(name="ainprof", aliases=["ainpfp"], hidden=True)
    async def ainprof_prefix(self, ctx: commands.Context, *, name: str | None = None) -> None:
        if not await configured_owner(self.bot, ctx.author):
            await self.glass_reply(ctx, "Owner Only", "Only users listed in `OWNER_IDS` can change the bot profile.")
            return
        if not ctx.message.attachments:
            await self.glass_reply(ctx, "Missing Image", "Attach an image, then run `ainprof optional new name`.")
            return
        image_bytes = await ctx.message.attachments[0].read()
        kwargs: dict[str, object] = {"avatar": image_bytes}
        if name:
            kwargs["username"] = name.strip()[:32]
        try:
            await self.bot.user.edit(**kwargs)
        except discord.HTTPException as exc:
            await self.glass_reply(ctx, "Profile Error", f"I could not update the bot profile: `{type(exc).__name__}`")
            return
        await self.glass_reply(ctx, "Profile Updated", "Changed bot avatar.")

    def owned_channel(self, member: discord.Member) -> discord.VoiceChannel | None:
        if member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
            channel = member.voice.channel
            owner = self.vc_owners.get(channel.id)
            if owner in {None, member.id} or member.guild_permissions.manage_channels:
                return channel
        return None

    def find_voice_channel(self, guild: discord.Guild, name_or_id: str) -> discord.VoiceChannel | None:
        query = name_or_id.strip()
        if query.startswith("<#") and query.endswith(">") and query[2:-1].isdigit():
            channel = guild.get_channel(int(query[2:-1]))
            return channel if isinstance(channel, discord.VoiceChannel) else None
        if query.isdigit():
            channel = guild.get_channel(int(query))
            return channel if isinstance(channel, discord.VoiceChannel) else None
        lowered = query.lower()
        for channel in guild.voice_channels:
            if channel.name.lower() == lowered:
                return channel
        for channel in guild.voice_channels:
            if lowered in channel.name.lower():
                return channel
        return None

    async def can_drag_members(self, actor: discord.Member) -> bool:
        return actor.guild_permissions.move_members or actor.guild_permissions.administrator or await configured_owner(self.bot, actor)

    async def drag_channel_members(self, actor: discord.Member, source: discord.VoiceChannel, destination: discord.VoiceChannel) -> tuple[int, int]:
        moved = 0
        failed = 0
        for member in list(source.members):
            try:
                await member.move_to(destination, reason=f"Drag all by {actor}")
                moved += 1
            except discord.HTTPException:
                failed += 1
        return moved, failed

    @staticmethod
    def format_vc_time(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            return f"{hours:,}h {minutes:02d}m"
        return f"{minutes}m"

    async def prefix_owned_channel(self, ctx: commands.Context) -> discord.VoiceChannel | None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return None
        channel = self.owned_channel(ctx.author)
        if not channel:
            await self.glass_reply(ctx, "No VC Control")
            return None
        return channel

    @commands.group(name="vc", invoke_without_command=True)
    async def vc_prefix(self, ctx: commands.Context) -> None:
        await self.glass_reply(ctx, "VC Commands", "`,vc claim`, `,vc lock`, `,vc unlock`, `,vc hide`, `,vc reveal`, `,vc rename <name>`, `,vc limit <number>`, `,vc permit @user`, `,vc reject @user`, `,vc transfer @user`, `,vc leaderboard`")

    @vc_prefix.command(name="claim")
    async def vc_prefix_claim(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await self.glass_reply(ctx, "Join A Voice Channel")
            return
        self.vc_owners[ctx.author.voice.channel.id] = ctx.author.id
        await self.glass_reply(ctx, "VC Claimed")

    @vc_prefix.command(name="rename")
    async def vc_prefix_rename(self, ctx: commands.Context, *, name: str) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.edit(name=name[:90])
            await self.glass_reply(ctx, "VC Renamed")

    @vc_prefix.command(name="lock")
    async def vc_prefix_lock(self, ctx: commands.Context) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(ctx.guild.default_role, connect=False)
            await self.glass_reply(ctx, "VC Locked")

    @vc_prefix.command(name="unlock")
    async def vc_prefix_unlock(self, ctx: commands.Context) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(ctx.guild.default_role, connect=None)
            await self.glass_reply(ctx, "VC Unlocked")

    @vc_prefix.command(name="hide")
    async def vc_prefix_hide(self, ctx: commands.Context) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(ctx.guild.default_role, view_channel=False)
            await self.glass_reply(ctx, "VC Hidden")

    @vc_prefix.command(name="reveal")
    async def vc_prefix_reveal(self, ctx: commands.Context) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(ctx.guild.default_role, view_channel=None)
            await self.glass_reply(ctx, "VC Revealed")

    @vc_prefix.command(name="limit")
    async def vc_prefix_limit(self, ctx: commands.Context, limit: int) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.edit(user_limit=max(0, min(99, limit)))
            await self.glass_reply(ctx, "VC Limit Updated")

    @vc_prefix.command(name="bitrate")
    async def vc_prefix_bitrate(self, ctx: commands.Context, bitrate: int) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.edit(bitrate=max(8000, min(384000, bitrate)))
            await self.glass_reply(ctx, "VC Bitrate Updated")

    @vc_prefix.command(name="permit")
    async def vc_prefix_permit(self, ctx: commands.Context, member: discord.Member) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(member, connect=True, view_channel=True)
            await self.glass_reply(ctx, "Member Permitted")

    @vc_prefix.command(name="reject")
    async def vc_prefix_reject(self, ctx: commands.Context, member: discord.Member) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            await channel.set_permissions(member, connect=False)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
            await self.glass_reply(ctx, "Member Rejected")

    @vc_prefix.command(name="transfer")
    async def vc_prefix_transfer(self, ctx: commands.Context, member: discord.Member) -> None:
        channel = await self.prefix_owned_channel(ctx)
        if channel:
            self.vc_owners[channel.id] = member.id
            await self.glass_reply(ctx, "VC Transferred")

    @vc_prefix.command(name="godmode")
    async def vc_prefix_godmode(self, ctx: commands.Context, member: discord.Member) -> None:
        if not isinstance(ctx.author, discord.Member) or not (ctx.author.guild_permissions.administrator or await configured_owner(self.bot, ctx.author)):
            await self.glass_reply(ctx, "Missing Permission")
            return
        settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
        ids = settings.get("vc_godmode", [])
        if member.id not in ids:
            ids.append(member.id)
        await self.bot.db.set_settings_value(ctx.guild.id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await self.glass_reply(ctx, "VC God Mode")

    @vc_prefix.command(name="godmodeoff")
    async def vc_prefix_godmodeoff(self, ctx: commands.Context, member: discord.Member) -> None:
        if not isinstance(ctx.author, discord.Member) or not (ctx.author.guild_permissions.administrator or await configured_owner(self.bot, ctx.author)):
            await self.glass_reply(ctx, "Missing Permission")
            return
        settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
        ids = [uid for uid in settings.get("vc_godmode", []) if uid != member.id]
        await self.bot.db.set_settings_value(ctx.guild.id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await self.glass_reply(ctx, "VC God Mode Removed")

    async def save_vc_session_time(self, guild_id: int, user_id: int, now: float) -> None:
        key = (guild_id, user_id)
        session = self.vc_sessions.get(key)
        if not session:
            return
        elapsed = max(0, int(now - float(session["last_at"])))
        if elapsed <= 0:
            session["last_at"] = now
            return
        await self.bot.db.execute(
            "INSERT INTO voice_stats(guild_id,user_id,voice_seconds,stream_seconds,camera_seconds) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id,user_id) DO UPDATE SET "
            "voice_seconds=voice_seconds+excluded.voice_seconds,"
            "stream_seconds=stream_seconds+excluded.stream_seconds,"
            "camera_seconds=camera_seconds+excluded.camera_seconds",
            guild_id,
            user_id,
            elapsed,
            elapsed if bool(session.get("streaming")) else 0,
            elapsed if bool(session.get("camera")) else 0,
        )
        session["last_at"] = now

    async def flush_guild_vc_sessions(self, guild_id: int) -> None:
        now = time.time()
        for session_guild_id, user_id in list(self.vc_sessions):
            if session_guild_id == guild_id:
                await self.save_vc_session_time(guild_id, user_id, now)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        now = time.time()
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        self.vc_sessions[(guild.id, member.id)] = {"last_at": now, "streaming": bool(member.voice and member.voice.self_stream), "camera": bool(member.voice and member.voice.self_video)}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot:
            return
        key = (member.guild.id, member.id)
        now = time.time()
        if key in self.vc_sessions:
            await self.save_vc_session_time(member.guild.id, member.id, now)
        if after.channel is None:
            self.vc_sessions.pop(key, None)
            return
        self.vc_sessions[key] = {"last_at": now, "streaming": bool(after.self_stream), "camera": bool(after.self_video)}

    @vc.command(name="claim", description="Claim an ownerless temporary voice channel")
    async def vc_claim(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await self.glass_response(interaction, "Join A Voice Channel", "Hop into a voice channel first, then use this command.")
            return
        self.vc_owners[member.voice.channel.id] = member.id
        await self.glass_response(interaction, "VC Claimed")

    @vc.command(name="rename", description="Rename your temporary voice channel")
    async def vc_rename(self, interaction: discord.Interaction, name: str) -> None:
        channel = self.owned_channel(interaction.user)
        if not channel:
            await self.glass_response(interaction, "No VC Control", "You do not own your current voice channel.")
            return
        await channel.edit(name=name[:90])
        await self.glass_response(interaction, "VC Renamed")

    @vc.command(name="lock", description="Lock your temporary voice channel")
    async def vc_lock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
        await self.glass_response(interaction, "VC Locked")

    @vc.command(name="unlock", description="Unlock your temporary voice channel")
    async def vc_unlock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
        await self.glass_response(interaction, "VC Unlocked")

    @vc.command(name="hide", description="Hide your temporary voice channel")
    async def vc_hide(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await self.glass_response(interaction, "VC Hidden")

    @vc.command(name="reveal", description="Reveal your temporary voice channel")
    async def vc_reveal(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await self.glass_response(interaction, "VC Revealed")

    @vc.command(name="limit", description="Set your temporary voice user limit")
    async def vc_limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(user_limit=limit)
        await self.glass_response(interaction, "VC Limit Updated")

    @vc.command(name="bitrate", description="Set your temporary voice bitrate")
    async def vc_bitrate(self, interaction: discord.Interaction, bitrate: app_commands.Range[int, 8000, 384000]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(bitrate=bitrate)
        await self.glass_response(interaction, "VC Bitrate Updated")

    @vc.command(name="drag", description="Move everyone from one voice channel to another")
    @app_commands.default_permissions(move_members=True)
    async def vc_drag(self, interaction: discord.Interaction, source: discord.VoiceChannel, destination: discord.VoiceChannel) -> None:
        if not isinstance(interaction.user, discord.Member) or not await self.can_drag_members(interaction.user):
            await self.glass_response(interaction, "Missing Permission", "You need `Move Members`, Admin, or `OWNER_IDS` to use this.")
            return
        await interaction.response.defer(ephemeral=True)
        moved, failed = await self.drag_channel_members(interaction.user, source, destination)
        e = embed("Drag Complete", f"{pulse_line()}\n\nMoved `{moved}` member(s) from **{source.name}** to **{destination.name}**.")
        if failed:
            e.add_field(name="Failed", value=f"`{failed}` member(s) could not be moved.", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @commands.command(name="drag", aliases=["dragall", "moveall"])
    async def drag_prefix(self, ctx: commands.Context, *, route: str) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not await self.can_drag_members(ctx.author):
            await self.glass_reply(ctx, "Missing Permission", "You need `Move Members`, Admin, or `OWNER_IDS` to use this.")
            return
        if " to " not in route.lower():
            await self.glass_reply(ctx, "Wrong Format", "Use `,drag old call to new call`.")
            return
        left, right = route.rsplit(" to ", 1)
        source = self.find_voice_channel(ctx.guild, left)
        destination = self.find_voice_channel(ctx.guild, right)
        if source is None or destination is None:
            await self.glass_reply(ctx, "VC Not Found", "I could not find one of those voice channels.")
            return
        moved, failed = await self.drag_channel_members(ctx.author, source, destination)
        e = embed("Drag Complete", f"{pulse_line()}\n\nMoved `{moved}` member(s) from **{source.name}** to **{destination.name}**.")
        if failed:
            e.add_field(name="Failed", value=f"`{failed}` member(s) could not be moved.", inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @vc.command(name="permit", description="Allow a member into your temporary voice channel")
    async def vc_permit(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(member, connect=True, view_channel=True)
        await self.glass_response(interaction, "Member Permitted")

    @vc.command(name="reject", description="Block a member from your temporary voice channel")
    async def vc_reject(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(member, connect=False)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
        await self.glass_response(interaction, "Member Rejected")

    @vc.command(name="transfer", description="Transfer your temporary voice channel ownership")
    async def vc_transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            self.vc_owners[channel.id] = member.id
        await self.glass_response(interaction, "VC Transferred")

    @vc.command(name="godmode", description="Protect a member from bot VC reject/control commands")
    @app_admin()
    async def vc_godmode(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = settings.get("vc_godmode", [])
        if member.id not in ids:
            ids.append(member.id)
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await self.glass_response(interaction, "VC God Mode")

    @vc.command(name="godmodeoff", description="Remove VC god mode from a member")
    @app_admin()
    async def vc_godmodeoff(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = [uid for uid in settings.get("vc_godmode", []) if uid != member.id]
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await self.glass_response(interaction, "VC God Mode Removed")

    @vc.command(name="godmodelist", description="Show members with VC god mode")
    @app_admin()
    async def vc_godmodelist(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        value = ", ".join(f"<@{uid}>" for uid in settings.get("vc_godmode", [])) or "No VC God Mode members."
        await self.glass_response(interaction, "VC God Mode List", value)

    @vc.command(name="leaderboard", description="Show voice, stream, and camera hour leaders")
    async def vc_leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.flush_guild_vc_sessions(interaction.guild_id)
        rows = await self.bot.db.fetchall(
            "SELECT user_id,voice_seconds,stream_seconds,camera_seconds FROM voice_stats WHERE guild_id=? ORDER BY voice_seconds DESC LIMIT 10",
            interaction.guild_id,
        )
        e = embed("VC Hours Leaderboard", f"Top `{len(rows)}` members by total voice time.")
        if not rows:
            e.description = "No VC time has been tracked yet."
        for index, row in enumerate(rows, start=1):
            e.add_field(
                name=f"{index}. <@{row['user_id']}>",
                value=f"`Voice` {self.format_vc_time(row['voice_seconds'])}\n`Stream` {self.format_vc_time(row['stream_seconds'])}\n`Camera` {self.format_vc_time(row['camera_seconds'])}",
                inline=False,
            )
        await interaction.followup.send(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VcMusicTools(bot))
