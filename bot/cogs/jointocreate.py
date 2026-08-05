from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin
from bot.core.utils import DEFAULT_COLOR, embed, pulse_line, style_embed, theme_color_from_data


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
        glass_labels = {
            "Claim": "Glass Claim",
            "Boost Bitrate": "Glass Bitrate",
            "Boost Privacy": "Glass Privacy",
            "Play Music": "Glass Music",
            "Purple Pulse": "Glass Pulse",
        }
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.label in glass_labels:
                    item.label = glass_labels[item.label]
                if item.style in {discord.ButtonStyle.primary, discord.ButtonStyle.success}:
                    item.style = discord.ButtonStyle.secondary
                if item.label in {"Glass Claim", "Unlock", "Glass Bitrate", "Glass Privacy", "Glass Music", "Glass Pulse"}:
                    item.emoji = None

    async def channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return None
        channel = interaction.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("That temp voice channel is gone.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="Claim", emoji="👑", style=discord.ButtonStyle.primary)
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

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcRenameModal(self.cog, channel))

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary)
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcLimitModal(self.cog, channel))

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.danger)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=False)
        await interaction.response.send_message("Voice channel locked.", ephemeral=True)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.success)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=None)
        await interaction.response.send_message("Voice channel unlocked.", ephemeral=True)

    @discord.ui.button(label="Hide", emoji="🙈", style=discord.ButtonStyle.secondary)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice channel hidden.", ephemeral=True)

    @discord.ui.button(label="Reveal", emoji="👁️", style=discord.ButtonStyle.secondary)
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=None)
        await interaction.response.send_message("Voice channel revealed.", ephemeral=True)

    @discord.ui.button(label="Boost Bitrate", style=discord.ButtonStyle.primary)
    async def boost_bitrate(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_use_booster_perk(interaction, channel):
            return
        bitrate = min(channel.guild.bitrate_limit, 128000)
        await channel.edit(bitrate=int(bitrate), reason=f"Booster VC bitrate by {interaction.user}")
        await interaction.response.send_message("Booster bitrate applied to this VC.", ephemeral=True)

    @discord.ui.button(label="Boost Privacy", style=discord.ButtonStyle.primary)
    async def boost_privacy(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_use_booster_perk(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=False, view_channel=True)
        await interaction.response.send_message("Booster privacy turned on. Use Unlock when you want to open it again.", ephemeral=True)

    @discord.ui.button(label="Play Music", style=discord.ButtonStyle.success)
    async def play_music(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        await self.cog.start_music_panel(interaction, channel)

    @discord.ui.button(label="Purple Pulse", style=discord.ButtonStyle.primary)
    async def purple_pulse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        await interaction.response.send_message(embed=self.cog.pulse_embed(channel.guild), ephemeral=True)


class JoinToCreate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.owners: dict[int, int] = {}
        self.theme_colors: dict[int, int] = {}
        self.theme_options: dict[int, dict] = {}
        self.cleanup_empty_jtc_channels.start()

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
        theme = self.theme_options.get(channel.guild.id, {})
        e = embed("Voice Glass Panel", f"{pulse_line()}\n\nOwner: {owner.mention}\nUse the frosted controls below to control {channel.mention}.", self.theme_color(channel.guild))
        e.add_field(name="Quick Controls", value="Claim, rename, set user limit, lock, unlock, hide, or reveal this temporary VC.", inline=False)
        e.add_field(name="Booster Perks", value="Boost Bitrate and Boost Privacy are booster-only VC tools. Mods can use them too.", inline=False)
        e.add_field(name="Music", value="Press Play Music to bring the bot into this VC and open the music panel.", inline=False)
        e.add_field(name="Style", value="Glass Pulse refreshes the red glass frame for this VC.", inline=False)
        if theme.get("effects", True):
            e.add_field(name="Live Detail", value="Barely translucent red background feel, white outline wording, and a glass-frame banner slot from `/theme banner`.", inline=False)
        e.set_footer(text="AinBot JTC | red glass interface")
        return style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))

    def pulse_embed(self, guild: discord.Guild | None) -> discord.Embed:
        theme = self.theme_options.get(guild.id, {}) if guild else {}
        e = embed("Glass Pulse", pulse_line(), self.theme_color(guild))
        e.add_field(name="VC Interface", value="This temp VC panel is using the red glass server theme.", inline=False)
        return style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))

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
        except discord.HTTPException:
            pass

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
                    await channel.delete(reason="Empty join-to-create channel")
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
        await self.warn_bad_vc_mute(member, before, after)
        if after.channel:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            template = settings.get("jtc_templates", {}).get(str(after.channel.id))
            if template:
                category = member.guild.get_channel(template.get("category_id") or 0)
                if not isinstance(category, discord.CategoryChannel):
                    category = after.channel.category
                channel = await member.guild.create_voice_channel(
                    template.get("name", "{user}'s room").format(user=member.display_name)[:90],
                    category=category,
                    user_limit=int(template.get("user_limit", 0)),
                    reason="Join-to-create",
                )
                self.owners[channel.id] = member.id
                temp_channels = settings.get("jtc_temp_channels", {})
                temp_channels[str(channel.id)] = {"owner_id": member.id, "lobby_id": after.channel.id}
                await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
                await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
                await member.move_to(channel)
                await self.send_control_panel(channel, member)
        if before.channel and not before.channel.members:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            temp_channels = settings.get("jtc_temp_channels", {})
            is_temp_channel = before.channel.id in self.owners or str(before.channel.id) in temp_channels
            if not is_temp_channel:
                return
            self.owners.pop(before.channel.id, None)
            temp_channels.pop(str(before.channel.id), None)
            await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
            await before.channel.delete(reason="Empty join-to-create channel")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JoinToCreate(bot))
