from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin
from bot.core.utils import DEFAULT_COLOR, embed, theme_color_from_data


class JtcRenameModal(discord.ui.Modal):
    def __init__(self, cog: "JoinToCreate", channel: discord.VoiceChannel) -> None:
        super().__init__(title="Rename Voice Channel")
        self.cog = cog
        self.channel = channel
        self.name_input = discord.ui.TextInput(label="New name", default=channel.name, max_length=90)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.cog.can_control(interaction, self.channel):
            return
        await self.channel.edit(name=str(self.name_input)[:90], reason=f"JTC rename by {interaction.user}")
        await interaction.response.send_message("Voice channel renamed.", ephemeral=True)


class JtcLimitModal(discord.ui.Modal):
    def __init__(self, cog: "JoinToCreate", channel: discord.VoiceChannel) -> None:
        super().__init__(title="Set User Limit")
        self.cog = cog
        self.channel = channel
        self.limit_input = discord.ui.TextInput(label="Limit", placeholder="0 for unlimited", default=str(channel.user_limit), max_length=2)
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.cog.can_control(interaction, self.channel):
            return
        try:
            limit = max(0, min(99, int(str(self.limit_input))))
        except ValueError:
            await interaction.response.send_message("Use a number from 0 to 99.", ephemeral=True)
            return
        await self.channel.edit(user_limit=limit, reason=f"JTC limit by {interaction.user}")
        await interaction.response.send_message(f"User limit set to `{limit}`.", ephemeral=True)


class JtcControlView(discord.ui.View):
    def __init__(self, cog: "JoinToCreate", channel_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id

    async def channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return None
        channel = interaction.channel if isinstance(interaction.channel, discord.VoiceChannel) else interaction.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("That temp voice channel is gone.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="Claim", emoji="👑", style=discord.ButtonStyle.primary, custom_id="jtc:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        self.cog.owners[channel.id] = interaction.user.id
        await self.cog.save_temp_owner(channel.guild, channel.id, interaction.user.id)
        await channel.set_permissions(interaction.user, manage_channels=True, connect=True, view_channel=True)
        await interaction.response.send_message(f"{interaction.user.mention} now owns this VC.", ephemeral=True)

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="jtc:rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcRenameModal(self.cog, channel))

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary, custom_id="jtc:limit")
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcLimitModal(self.cog, channel))

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="jtc:lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=False)
        await interaction.response.send_message("Voice channel locked.", ephemeral=True)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.success, custom_id="jtc:unlock")
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=None)
        await interaction.response.send_message("Voice channel unlocked.", ephemeral=True)

    @discord.ui.button(label="Hide", emoji="🙈", style=discord.ButtonStyle.secondary, custom_id="jtc:hide")
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice channel hidden.", ephemeral=True)

    @discord.ui.button(label="Reveal", emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="jtc:reveal")
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=None)
        await interaction.response.send_message("Voice channel revealed.", ephemeral=True)

    @discord.ui.button(label="Boost Bitrate", style=discord.ButtonStyle.primary, custom_id="jtc:boost_bitrate")
    async def boost_bitrate(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_use_booster_perk(interaction, channel):
            return
        bitrate = min(channel.guild.bitrate_limit, 128000)
        await channel.edit(bitrate=int(bitrate), reason=f"Booster VC bitrate by {interaction.user}")
        await interaction.response.send_message("Booster bitrate applied to this VC.", ephemeral=True)

    @discord.ui.button(label="Boost Privacy", style=discord.ButtonStyle.primary, custom_id="jtc:boost_privacy")
    async def boost_privacy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_use_booster_perk(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=False, view_channel=True)
        await interaction.response.send_message("Booster privacy turned on. Use Unlock when you want to open it again.", ephemeral=True)

    @discord.ui.button(label="Play Music", style=discord.ButtonStyle.success, custom_id="jtc:play_music")
    async def play_music(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        await self.cog.start_music_panel(interaction, channel)

class JoinToCreate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.owners: dict[int, int] = {}
        self.creating_for: set[int] = set()
        self.theme_colors: dict[int, int] = {}
        self.theme_options: dict[int, dict] = {}
        self.cleanup_empty_jtc_channels.start()

    async def cog_load(self) -> None:
        self.bot.add_view(JtcControlView(self, 0))

    def cog_unload(self) -> None:
        self.cleanup_empty_jtc_channels.cancel()

    jtc = app_commands.Group(name="jtc", description="Join-to-create voice channels")

    async def save_temp_owner(self, guild: discord.Guild, channel_id: int, owner_id: int) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        temp_channels = settings.get("jtc_temp_channels", {})
        data = temp_channels.setdefault(str(channel_id), {})
        data["owner_id"] = owner_id
        await self.bot.db.set_settings_value(guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)

    async def can_control(self, interaction: discord.Interaction, channel: discord.VoiceChannel, respond: bool = True) -> bool:
        if not isinstance(interaction.user, discord.Member):
            if respond:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return False
        settings = await self.bot.db.get_settings(channel.guild.id, self.bot.settings.default_prefix)
        saved = settings.get("jtc_temp_channels", {}).get(str(channel.id), {})
        owner_id = self.owners.get(channel.id) or saved.get("owner_id")
        if owner_id == interaction.user.id or interaction.user.guild_permissions.manage_channels:
            return True
        if respond:
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
        return False

    async def can_use_booster_perk(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> bool:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return False
        if not interaction.user.premium_since and not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("This is a booster-only VC perk. Mods can use it too.", ephemeral=True)
            return False
        return await self.can_control(interaction, channel)

    async def load_theme(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        self.theme_options[guild.id] = settings.get("theme", {})
        color = settings.get("theme", {}).get("color")
        if color:
            try:
                self.theme_colors[guild.id] = int(color)
                colors = getattr(self.bot, "theme_colors", {})
                colors[guild.id] = int(color)
                setattr(self.bot, "theme_colors", colors)
            except (TypeError, ValueError):
                pass

    def theme_color(self, guild: discord.Guild | None) -> discord.Color:
        if guild is None:
            return DEFAULT_COLOR
        theme = self.theme_options.get(guild.id) or getattr(self.bot, "theme_options", {}).get(guild.id, {})
        if theme.get("mode") == "fade":
            return theme_color_from_data(theme)
        cached = self.theme_colors.get(guild.id) or getattr(self.bot, "theme_colors", {}).get(guild.id)
        return discord.Color(int(cached)) if cached else DEFAULT_COLOR

    def control_embed(self, channel: discord.VoiceChannel, owner: discord.Member) -> discord.Embed:
        e = embed("Voice Channel Controls", f"Owner: {owner.mention}\nChannel: {channel.mention}", self.theme_color(channel.guild))
        e.add_field(name="Channel", value="Claim · Rename · Limit · Lock · Unlock · Hide · Reveal", inline=False)
        e.add_field(name="Extras", value="Boost Bitrate · Boost Privacy · Play Music", inline=False)
        e.set_footer(text="Only the VC owner or server moderators can use these controls.")
        return e

    async def start_music_panel(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if interaction.user.voice is None or interaction.user.voice.channel is None or interaction.user.voice.channel.id != channel.id:
            await interaction.response.send_message("Join this temp VC first, then press Play Music.", ephemeral=True)
            return
        music = self.bot.get_cog("Music")
        if music is None or not hasattr(music, "send_or_update_panel"):
            await interaction.response.send_message("Music is not loaded on this bot.", ephemeral=True)
            return
        vc = channel.guild.voice_client
        try:
            if vc is None:
                await channel.connect(self_deaf=True)
            elif vc.channel and vc.channel.id != channel.id:
                await vc.move_to(channel)
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"I could not join this VC: `{type(exc).__name__}`", ephemeral=True)
            return
        await music.send_or_update_panel(channel.guild, channel)
        await interaction.response.send_message("Music panel opened for this VC.", ephemeral=True)

    async def voice_mute_actor(self, guild: discord.Guild, target: discord.Member) -> discord.Member | None:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                if entry.target and entry.target.id == target.id and (discord.utils.utcnow() - entry.created_at).total_seconds() <= 10:
                    return entry.user if isinstance(entry.user, discord.Member) else None
        except discord.HTTPException:
            return None
        return None

    async def warn_bad_vc_mute(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.mute or not after.mute:
            return
        channel = after.channel or before.channel
        if not isinstance(channel, discord.VoiceChannel):
            return
        actor = await self.voice_mute_actor(member.guild, member)
        if actor is None or actor.bot:
            return
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        saved = settings.get("jtc_temp_channels", {}).get(str(channel.id), {})
        owner_id = self.owners.get(channel.id) or saved.get("owner_id")
        if actor.id == owner_id:
            return
        now = time.time()
        all_strikes = settings.get("vc_mute_strikes", {})
        strike_key = f"{actor.id}:{channel.id}"
        strikes = [float(stamp) for stamp in all_strikes.get(strike_key, []) if now - float(stamp) < 1800]
        strikes.append(now)
        all_strikes[strike_key] = strikes[-3:]
        await self.bot.db.set_settings_value(member.guild.id, "vc_mute_strikes", all_strikes, self.bot.settings.default_prefix)
        count = len(all_strikes[strike_key])
        title = "VC Mute Final Warning" if count >= 3 else "VC Mute Warning"
        text = (
            f"{actor.mention}, you server-muted {member.mention} in a VC you do not own.\n"
            f"Strikes in this VC: `{count}/3`\n"
            "Strikes reset after 30 minutes."
        )
        if count >= 3:
            text += "\nThis is the last warning for this VC."
        try:
            await channel.send(embed=embed(title, text))
        except discord.HTTPException:
            pass

    async def send_control_panel(self, channel: discord.VoiceChannel, owner: discord.Member) -> None:
        try:
            await self.load_theme(channel.guild)
            await channel.send(content=owner.mention, embed=self.control_embed(channel, owner), view=JtcControlView(self, channel.id))
        except discord.HTTPException as exc:
            self.bot.log.warning("Could not post JTC controls in %s (%s): %s", channel.name, channel.id, exc)

    @tasks.loop(seconds=45)
    async def cleanup_empty_jtc_channels(self) -> None:
        for guild in self.bot.guilds:
            settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
            temp_channels = settings.get("jtc_temp_channels", {})
            changed = False
            for channel_id in list(temp_channels):
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    temp_channels.pop(channel_id, None)
                    self.owners.pop(int(channel_id), None)
                    changed = True
                    continue
                if isinstance(channel, discord.VoiceChannel) and not channel.members:
                    temp_channels.pop(channel_id, None)
                    self.owners.pop(channel.id, None)
                    changed = True
                    try:
                        await channel.delete(reason="Empty join-to-create channel")
                    except discord.HTTPException as exc:
                        self.bot.log.warning("Could not delete empty JTC channel %s: %s", channel.id, exc)
            if changed:
                await self.bot.db.set_settings_value(guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)

    @cleanup_empty_jtc_channels.before_loop
    async def before_cleanup_empty_jtc_channels(self) -> None:
        await self.bot.wait_until_ready()

    @jtc.command(name="setup", description="Set a voice channel as a join-to-create template")
    @app_admin()
    async def setup_template(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        name: str = "{user}'s room",
        user_limit: int = 0,
        output_category: discord.CategoryChannel | None = None,
    ) -> None:
        me = interaction.guild.me
        if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.move_members:
            await interaction.response.send_message("JTC needs **Manage Channels** and **Move Members** before setup can work.", ephemeral=True)
            return
        user_limit = max(0, min(99, int(user_limit)))
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        templates[str(channel.id)] = {
            "name": name,
            "user_limit": user_limit,
            "category_id": output_category.id if output_category else None,
        }
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", templates, self.bot.settings.default_prefix)
        await interaction.response.send_message("Join-to-create template saved.", ephemeral=True)

    @jtc.command(name="category", description="Set where temporary JTC voice channels are created")
    @app_admin()
    async def category(self, interaction: discord.Interaction, lobby: discord.VoiceChannel, output_category: discord.CategoryChannel) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        template = templates.setdefault(str(lobby.id), {"name": "{user}'s room", "user_limit": 0})
        template["category_id"] = output_category.id
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", templates, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Temporary channels from {lobby.mention} will be created in **{output_category.name}**.", ephemeral=True)

    @jtc.command(name="config", description="Show current join-to-create setup")
    @app_admin()
    async def config(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        e = embed("JTC Config")
        if not templates:
            e.description = "Join-to-create is not configured yet."
        for channel_id, template in templates.items():
            lobby = interaction.guild.get_channel(int(channel_id))
            category = interaction.guild.get_channel(template.get("category_id") or 0)
            template_name = template.get("name", "{user}'s room")
            e.add_field(
                name=lobby.mention if lobby else f"Missing lobby `{channel_id}`",
                value=(
                    f"Name: `{template_name}`\n"
                    f"User limit: `{template.get('user_limit', 0)}`\n"
                    f"Output category: `{category.name if isinstance(category, discord.CategoryChannel) else 'Same as lobby'}`"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @jtc.command(name="disable", description="Disable join-to-create")
    @app_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", {}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Join-to-create disabled.", ephemeral=True)

    @jtc.command(name="claim", description="Claim the current temporary voice channel")
    async def claim(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join your temporary channel first.", ephemeral=True)
            return
        channel = member.voice.channel
        if channel.id not in self.owners:
            settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
            saved = settings.get("jtc_temp_channels", {}).get(str(channel.id), {})
            if saved.get("owner_id"):
                self.owners[channel.id] = int(saved["owner_id"])
        if channel.id not in self.owners:
            await interaction.response.send_message("This is not a managed temporary channel.", ephemeral=True)
            return
        self.owners[channel.id] = member.id
        await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
        await interaction.response.send_message("You now own this channel.", ephemeral=True)

    @jtc.command(name="rename", description="Rename your temporary voice channel")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or member.voice.channel.id not in self.owners:
            await interaction.response.send_message("Join your temporary channel first.", ephemeral=True)
            return
        if self.owners[member.voice.channel.id] != member.id and not member.guild_permissions.manage_channels:
            await interaction.response.send_message("Only the owner or moderators can rename this channel.", ephemeral=True)
            return
        await member.voice.channel.edit(name=name[:90])
        await interaction.response.send_message("Channel renamed.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot:
            return
        await self.warn_bad_vc_mute(member, before, after)
        if after.channel:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            template = settings.get("jtc_templates", {}).get(str(after.channel.id))
            if template and member.id not in self.creating_for:
                me = member.guild.me
                if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.move_members:
                    try:
                        await member.send(f"JTC could not create your room in **{member.guild.name}**. The bot needs Manage Channels and Move Members.")
                    except discord.HTTPException:
                        pass
                    self.bot.log.warning("JTC blocked in guild %s: missing Manage Channels or Move Members", member.guild.id)
                    return
                self.creating_for.add(member.id)
                category = member.guild.get_channel(template.get("category_id") or 0)
                if not isinstance(category, discord.CategoryChannel):
                    category = after.channel.category
                channel = None
                try:
                    room_name = str(template.get("name", "{user}'s room")).replace("{user}", member.display_name)[:90]
                    channel = await member.guild.create_voice_channel(
                        room_name or f"{member.display_name}'s room",
                        category=category,
                        user_limit=max(0, min(99, int(template.get("user_limit", 0)))),
                        reason="Join-to-create",
                    )
                    await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
                    await member.move_to(channel, reason="Join-to-create")
                    self.owners[channel.id] = member.id
                    temp_channels = settings.get("jtc_temp_channels", {})
                    temp_channels[str(channel.id)] = {"owner_id": member.id, "lobby_id": after.channel.id}
                    await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
                    await self.send_control_panel(channel, member)
                except (discord.Forbidden, discord.HTTPException, ValueError) as exc:
                    self.bot.log.exception("JTC creation failed in guild %s: %s", member.guild.id, exc)
                    if channel is not None:
                        try:
                            await channel.delete(reason="JTC creation failed")
                        except discord.HTTPException:
                            pass
                    try:
                        await member.send(f"JTC could not create your room in **{member.guild.name}**. Ask an admin to run `/doctor` and `/checkperms`.")
                    except discord.HTTPException:
                        pass
                finally:
                    self.creating_for.discard(member.id)
        if before.channel and not before.channel.members:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            temp_channels = settings.get("jtc_temp_channels", {})
            is_temp_channel = before.channel.id in self.owners or str(before.channel.id) in temp_channels
            if not is_temp_channel:
                return
            self.owners.pop(before.channel.id, None)
            temp_channels.pop(str(before.channel.id), None)
            await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
            try:
                await before.channel.delete(reason="Empty join-to-create channel")
            except discord.HTTPException as exc:
                self.bot.log.warning("Could not delete empty JTC channel %s: %s", before.channel.id, exc)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JoinToCreate(bot))
