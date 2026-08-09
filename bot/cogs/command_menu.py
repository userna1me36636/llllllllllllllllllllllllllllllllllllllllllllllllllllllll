from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner
from bot.core.utils import embed, is_multicolor_theme, parse_color, parse_duration, pulse_line, style_embed, theme_color_from_data


class VcOfferView(discord.ui.View):
    def __init__(self, offers: list[tuple[str, str, str]]) -> None:
        super().__init__(timeout=900)
        for label, price, url in offers:
            if url.startswith(("https://", "http://")):
                self.add_item(discord.ui.Button(label=f"{label} · ${price}", url=url))


class OwnerRoleConfirmView(discord.ui.View):
    def __init__(self, cog: "CommandMenu", action: str, role: discord.Role, target_role: discord.Role | None = None) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.action = action
        self.role = role
        self.target_role = target_role

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await configured_owner(self.cog.bot, interaction.user):
            return True
        await interaction.response.send_message("Only users in OWNER_IDS can confirm this.", ephemeral=True)
        return False

    @discord.ui.button(label="Confirm Role Edit", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        role = interaction.guild.get_role(self.role.id)
        if role is None:
            await interaction.response.edit_message(content="That role no longer exists.", view=None)
            return
        me = interaction.guild.me
        if me is None or role >= me.top_role:
            await interaction.response.edit_message(content="I cannot manage that role anymore. Move my bot role higher first.", view=None)
            return
        if self.action == "move_top":
            await role.edit(position=max(me.top_role.position - 1, 1), reason=f"Confirmed owner role move by {interaction.user}")
            await interaction.response.edit_message(content=f"Moved {role.mention} as high as I can place it.", view=None)
            return
        if self.target_role is not None:
            target = interaction.guild.get_role(self.target_role.id)
            if target is None:
                await interaction.response.edit_message(content="The target role no longer exists.", view=None)
                return
            if self.action == "move_above":
                await role.edit(position=min(target.position + 1, me.top_role.position - 1), reason=f"Confirmed owner role move by {interaction.user}")
                await interaction.response.edit_message(content=f"Moved {role.mention} above {target.mention}.", view=None)
                return
            if self.action == "move_below":
                await role.edit(position=target.position, reason=f"Confirmed owner role move by {interaction.user}")
                await interaction.response.edit_message(content=f"Moved {role.mention} below {target.mention}.", view=None)
                return
        permissions = role.permissions
        if self.action == "admin_on":
            permissions.administrator = True
        elif self.action == "admin_off":
            permissions.administrator = False
        elif self.action == "admin_toggle":
            permissions.administrator = not permissions.administrator
        await role.edit(permissions=permissions, reason=f"Confirmed owner role admin edit by {interaction.user}")
        await interaction.response.edit_message(content=f"Administrator is now `{permissions.administrator}` for {role.mention}.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Role edit cancelled.", view=None)


class CommandMenu(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reaction_roles: dict[tuple[int, int, str], int] = {}
        self.vc_owners: dict[int, int] = {}
        self.vc_sessions: dict[tuple[int, int], dict[str, float | bool]] = {}
        self.wizzpro_permissions = (
            "administrator",
            "ban_members",
            "kick_members",
            "manage_roles",
            "manage_channels",
            "manage_guild",
            "manage_webhooks",
            "moderate_members",
            "mute_members",
            "deafen_members",
            "move_members",
        )

    async def send_vc_reject_offer(self, member: discord.Member, channel: discord.VoiceChannel) -> tuple[bool, str]:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        offer = settings.get("vc_reject_offer", {})
        if not offer.get("enabled", True):
            return False, "VC Reject DM is turned off in the dashboard."
        defaults = {
            "title": "Voice Access Options",
            "message": "You were removed from a temporary voice channel. If you want additional VC access, use one of the options below.",
            "vc_perms_price": "15", "anti_reject_price": "20", "godmode_price": "30", "all_price": "45",
        }
        data = {**defaults, **offer}
        offers = [
            ("VC Perms", str(data["vc_perms_price"]), str(data.get("vc_perms_url", ""))),
            ("Anti-Reject", str(data["anti_reject_price"]), str(data.get("anti_reject_url", ""))),
            ("Godmode", str(data["godmode_price"]), str(data.get("godmode_url", ""))),
            ("All Access", str(data["all_price"]), str(data.get("all_url", ""))),
        ]
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        public_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/") or (f"https://{railway_domain}" if railway_domain else "")
        signing_secret = getattr(self.bot.settings, "oauth_state_secret", None) or getattr(self.bot.settings, "dashboard_token", None)
        if public_url and signing_secret:
            payload = f"{member.guild.id}:{member.id}"
            signature = hmac.new(signing_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            shop_url = f"{public_url}/shop?" + urllib.parse.urlencode({"guild_id": str(member.guild.id), "user_id": str(member.id), "signature": signature})
            offers = [(label, price, f"{shop_url}&product={key}") for (label, price, _), key in zip(offers, ("vc_perms", "anti_reject", "godmode", "all"))]
        view = VcOfferView(offers)
        message = embed(str(data["title"])[:256], f"{str(data['message'])[:3000]}\n\nServer: **{member.guild.name}**\nVoice channel: **{channel.name}**")
        message.add_field(name="VC Perms", value=f"${data['vc_perms_price']} · Voice access permissions", inline=True)
        message.add_field(name="Anti-Reject", value=f"${data['anti_reject_price']} · Protected VC access", inline=True)
        message.add_field(name="Godmode", value=f"${data['godmode_price']} · Full VC protection", inline=True)
        message.add_field(name="All Access", value=f"${data['all_price']} · Complete access bundle", inline=True)
        message.set_footer(text="Purchases are handled by the linked website. Contact server staff with questions.")
        try:
            await member.send(embed=message, view=view if view.children else None)
            return True, ""
        except discord.Forbidden:
            return False, "Discord blocked the DM. The rejected member must allow server DMs and must not have the bot blocked."
        except discord.HTTPException:
            lines = [str(data["message"])[:1200], "", f"Server: {member.guild.name}", f"Voice channel: {channel.name}", ""]
            for label, price, url in offers:
                lines.append(f"{label}: ${price}" + (f" - {url}" if url.startswith(("https://", "http://")) else ""))
            try:
                await member.send("\n".join(lines)[:2000])
                return True, ""
            except discord.Forbidden:
                return False, "Discord blocked the DM. The rejected member must allow server DMs and must not have the bot blocked."
            except discord.HTTPException as retry_error:
                return False, f"Discord rejected the DM (HTTP {retry_error.status}, code {retry_error.code})."

    autorole = app_commands.Group(name="autorole", description="Automatic role for new members")
    channel = app_commands.Group(name="channel", description="Channel tools")
    chatrevive = app_commands.Group(name="chatrevive", description="Revive quiet chats")
    logs = app_commands.Group(name="logs", description="Server logs")
    ownerrole = app_commands.Group(name="ownerrole", description="OWNER_IDS only high role tools")
    reactionrole = app_commands.Group(name="reactionrole", description="Reaction roles")
    remind = app_commands.Group(name="remind", description="Personal reminders")
    role = app_commands.Group(name="role", description="Role tools")
    theme = app_commands.Group(name="theme", description="Change the bot's server style")
    vc = app_commands.Group(name="vc", description="Temporary voice controls")

    @app_commands.command(name="ping", description="Check whether the bot is online")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong: {round(self.bot.latency * 1000)}ms")

    async def save_theme_color(self, guild_id: int, color: discord.Color) -> None:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        theme["color"] = color.value
        theme["mode"] = "solid"
        await self.bot.db.set_settings_value(guild_id, "theme", theme, self.bot.settings.default_prefix)
        colors = getattr(self.bot, "theme_colors", {})
        colors[guild_id] = color.value
        setattr(self.bot, "theme_colors", colors)
        theme_options = getattr(self.bot, "theme_options", {})
        theme_options[guild_id] = theme
        setattr(self.bot, "theme_options", theme_options)

    async def save_theme_fade(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        theme["mode"] = "fade"
        theme["fade_speed"] = 10
        await self.bot.db.set_settings_value(guild_id, "theme", theme, self.bot.settings.default_prefix)
        theme_options = getattr(self.bot, "theme_options", {})
        theme_options[guild_id] = theme
        setattr(self.bot, "theme_options", theme_options)
        return theme

    async def save_theme_value(self, guild_id: int, key: str, value: object) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        theme[key] = value
        await self.bot.db.set_settings_value(guild_id, "theme", theme, self.bot.settings.default_prefix)
        return theme

    async def theme_data(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("theme", {})

    @theme.command(name="color", description="Change the bot embed color for this server")
    @app_admin()
    async def theme_color(self, interaction: discord.Interaction, color: str) -> None:
        if is_multicolor_theme(color):
            theme = await self.save_theme_fade(interaction.guild_id)
            e = embed("Theme Updated", f"{pulse_line()}\n\nServer bot theme changed to **multicolor fade**.", theme_color_from_data(theme))
            e.add_field(name="Preview", value="New embeds will slowly rotate through red, purple, blue, green, and gold.", inline=False)
            await interaction.response.send_message(embed=style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True)), ephemeral=True)
            return
        try:
            parsed = parse_color(color)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self.save_theme_color(interaction.guild_id, parsed)
        e = embed("Theme Updated", f"{pulse_line()}\n\nServer bot color changed to `{color}`.", parsed)
        e.add_field(name="Preview", value="Music panels, JTC panels, and new feature embeds will use this color.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="preview", description="Preview the current bot theme")
    async def theme_preview(self, interaction: discord.Interaction) -> None:
        theme = await self.theme_data(interaction.guild_id)
        color = theme_color_from_data(theme, discord.Color(11146790))
        e = embed("Theme Preview", pulse_line(), color)
        e.add_field(name="Mode", value="Multicolor fade" if theme.get("mode") == "fade" else "Solid color", inline=True)
        e.add_field(name="Effects", value="On" if theme.get("effects", True) else "Off", inline=True)
        e.add_field(name="Banner", value="Set" if theme.get("banner_url") else "Not set", inline=True)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="banner", description="Set an image/GIF banner for flashy bot panels")
    @app_admin()
    async def theme_banner(self, interaction: discord.Interaction, url: str | None = None) -> None:
        if url and not url.startswith(("http://", "https://")):
            await interaction.response.send_message("Use a direct image/GIF link that starts with http or https.", ephemeral=True)
            return
        theme = await self.save_theme_value(interaction.guild_id, "banner_url", url or "")
        color = theme_color_from_data(theme, discord.Color(11146790))
        e = embed("Theme Banner Updated", "Panel banner cleared." if not url else "New panel banner saved.", color)
        style_embed(e, banner_url=url, flashy=theme.get("effects", True))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @theme.command(name="effects", description="Turn flashy panel effects on or off")
    @app_admin()
    async def theme_effects(self, interaction: discord.Interaction, enabled: bool = True) -> None:
        theme = await self.save_theme_value(interaction.guild_id, "effects", enabled)
        color = theme_color_from_data(theme, discord.Color(11847423))
        e = embed("Theme Effects Updated", f"Flashy panel effects are now **{'on' if enabled else 'off'}**.", color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=enabled)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.command(name="ainrename", hidden=True)
    async def ainrename_prefix(self, ctx: commands.Context, *, name: str) -> None:
        if not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Only users listed in OWNER_IDS can use this.", mention_author=False)
            return
        clean_name = name.strip()[:32]
        if len(clean_name) < 2:
            await ctx.reply("Use a name with at least 2 characters.", mention_author=False)
            return
        try:
            await self.bot.user.edit(username=clean_name)
        except discord.HTTPException as exc:
            await ctx.reply(f"I could not rename the bot: `{type(exc).__name__}: {str(exc)[:160]}`", mention_author=False)
            return
        await ctx.reply(embed=embed("Profile Updated", f"Bot name changed to **{clean_name}**."), mention_author=False)

    @commands.command(name="ainprof", aliases=["ainpfp"], hidden=True)
    async def ainprof_prefix(self, ctx: commands.Context, *, name: str | None = None) -> None:
        if not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Only users listed in OWNER_IDS can use this.", mention_author=False)
            return
        if not ctx.message.attachments:
            await ctx.reply("Attach an image, then run `ainprof optional new name`.", mention_author=False)
            return
        attachment = ctx.message.attachments[0]
        if not (attachment.content_type or "").startswith("image/"):
            await ctx.reply("Attach a PNG/JPG/WebP image.", mention_author=False)
            return
        image_bytes = await attachment.read()
        kwargs: dict[str, object] = {"avatar": image_bytes}
        if name:
            kwargs["username"] = name.strip()[:32]
        try:
            await self.bot.user.edit(**kwargs)
        except discord.HTTPException as exc:
            await ctx.reply(f"I could not update the bot profile: `{type(exc).__name__}: {str(exc)[:160]}`", mention_author=False)
            return
        label = f" and name to **{kwargs['username']}**" if "username" in kwargs else ""
        await ctx.reply(embed=embed("Profile Updated", f"Changed bot avatar{label}."), mention_author=False)

    @commands.group(name="theme", invoke_without_command=True)
    async def theme_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("Use `theme color glassred`, `theme color #aa1626`, or `theme preview`.", mention_author=False)

    @theme_prefix.command(name="color")
    async def theme_prefix_color(self, ctx: commands.Context, color: str) -> None:
        if not ctx.author.guild_permissions.administrator and not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Administrator or OWNER_IDS only.", mention_author=False)
            return
        if is_multicolor_theme(color):
            theme = await self.save_theme_fade(ctx.guild.id)
            e = embed("Theme Updated", f"{pulse_line()}\n\nServer bot theme changed to **multicolor fade**.", theme_color_from_data(theme))
            e.add_field(name="Preview", value="New embeds will slowly rotate through red, purple, blue, green, and gold.", inline=False)
            await ctx.reply(embed=style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True)), mention_author=False)
            return
        try:
            parsed = parse_color(color)
        except ValueError as exc:
            await ctx.reply(str(exc), mention_author=False)
            return
        await self.save_theme_color(ctx.guild.id, parsed)
        e = embed("Theme Updated", f"{pulse_line()}\n\nServer bot color changed to `{color}`.", parsed)
        e.add_field(name="Preview", value="Music panels, JTC panels, and new feature embeds will use this color.", inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @theme_prefix.command(name="preview")
    async def theme_prefix_preview(self, ctx: commands.Context) -> None:
        theme = await self.theme_data(ctx.guild.id)
        color = theme_color_from_data(theme, discord.Color(11146790))
        e = embed("Theme Preview", pulse_line(), color)
        e.add_field(name="Mode", value="Multicolor fade" if theme.get("mode") == "fade" else "Solid color", inline=True)
        e.add_field(name="Effects", value="On" if theme.get("effects", True) else "Off", inline=True)
        e.add_field(name="Banner", value="Set" if theme.get("banner_url") else "Not set", inline=True)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
        await ctx.reply(embed=e, mention_author=False)

    @theme_prefix.command(name="banner")
    async def theme_prefix_banner(self, ctx: commands.Context, url: str | None = None) -> None:
        if not ctx.author.guild_permissions.administrator and not await configured_owner(self.bot, ctx.author):
            await ctx.reply("Administrator or OWNER_IDS only.", mention_author=False)
            return
        if url and not url.startswith(("http://", "https://")):
            await ctx.reply("Use a direct image/GIF link that starts with http or https.", mention_author=False)
            return
        theme = await self.save_theme_value(ctx.guild.id, "banner_url", url or "")
        color = theme_color_from_data(theme, discord.Color(11146790))
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
        color = theme_color_from_data(theme, discord.Color(11146790))
        e = embed("Theme Effects Updated", f"Flashy panel effects are now **{'on' if state else 'off'}**.", color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=state)
        await ctx.reply(embed=e, mention_author=False)

    @app_commands.command(name="sync", description="Owner only: refresh slash commands")
    async def sync(
        self,
        interaction: discord.Interaction,
        announce_channel: discord.TextChannel | None = None,
        message: str = "New bot update is live. Slash commands were refreshed and the newest features are ready.",
    ) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        global_synced = await self.bot.tree.sync()
        guild_synced = []
        if interaction.guild is not None:
            self.bot.tree.copy_global_to(guild=interaction.guild)
            guild_synced = await self.bot.tree.sync(guild=interaction.guild)
            settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
            channel = announce_channel
            if channel is not None:
                await self.bot.db.set_settings_value(interaction.guild_id, "sync_announce_channel", channel.id, self.bot.settings.default_prefix)
            elif settings.get("sync_announce_channel"):
                saved_channel = interaction.guild.get_channel(int(settings["sync_announce_channel"]))
                channel = saved_channel if isinstance(saved_channel, discord.TextChannel) else None
            if channel is not None:
                e = embed("Bot Update", message[:350])
                e.add_field(name="Slash Commands", value=f"`{len(guild_synced)}` server commands refreshed.", inline=True)
                e.add_field(name="Status", value="Online and ready.", inline=True)
                theme = settings.get("theme", {})
                style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))
                e.set_footer(text=f"Updated by {interaction.user}")
                try:
                    await channel.send(
                        content="@here",
                        embed=e,
                        allowed_mentions=discord.AllowedMentions(everyone=True, users=False, roles=False),
                    )
                except discord.HTTPException:
                    await interaction.followup.send("Synced commands, but I could not post the update announcement in that channel.", ephemeral=True)
                    return
        await interaction.followup.send(
            f"Synced {len(global_synced)} global commands and {len(guild_synced)} server commands.",
            ephemeral=True,
        )

    @autorole.command(name="set", description="Give new members a role automatically")
    @app_admin()
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        welcome = settings.get("welcome", {})
        welcome["autorole"] = role.id
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Autorole set to {role.mention}.", ephemeral=True)

    @autorole.command(name="off", description="Turn off autorole")
    @app_admin()
    async def autorole_off(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        welcome = settings.get("welcome", {})
        welcome["autorole"] = None
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome, self.bot.settings.default_prefix)
        await interaction.response.send_message("Autorole turned off.", ephemeral=True)

    @channel.command(name="lock", description="Lock the current text channel")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_lock(self, interaction: discord.Interaction) -> None:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message("Channel locked.", ephemeral=True)

    @channel.command(name="unlock", description="Unlock the current text channel")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_unlock(self, interaction: discord.Interaction) -> None:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message("Channel unlocked.", ephemeral=True)

    @channel.command(name="slowmode", description="Set channel slowmode seconds")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"Slowmode set to {seconds}s.", ephemeral=True)

    @chatrevive.command(name="enable", description="Post a revive message when chat is dry")
    @app_admin()
    async def chatrevive_enable(self, interaction: discord.Interaction, channel: discord.TextChannel, hours: app_commands.Range[int, 1, 168] = 12, message: str = "Chat has been quiet. What is everyone up to?") -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "chatrevive", {"enabled": True, "channel": channel.id, "hours": hours, "message": message}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Chat revive enabled.", ephemeral=True)

    @chatrevive.command(name="disable", description="Turn off chat revive")
    @app_admin()
    async def chatrevive_disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "chatrevive", {"enabled": False}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Chat revive disabled.", ephemeral=True)

    @logs.command(name="set", description="Set the server log channel")
    @app_admin()
    async def logs_set(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "log_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Logs will go to {channel.mention}.", ephemeral=True)

    @logs.command(name="off", description="Turn off server logs")
    @app_admin()
    async def logs_off(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "log_channel", None, self.bot.settings.default_prefix)
        await interaction.response.send_message("Logs turned off.", ephemeral=True)

    @reactionrole.command(name="add", description="Add a reaction role to a message")
    @app_admin()
    async def rr_add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role) -> None:
        message = await interaction.channel.fetch_message(int(message_id))
        await message.add_reaction(emoji)
        self.reaction_roles[(interaction.guild_id, message.id, emoji)] = role.id
        await interaction.response.send_message("Reaction role added for this runtime.", ephemeral=True)

    @reactionrole.command(name="remove", description="Remove a reaction role from a message")
    @app_admin()
    async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str) -> None:
        self.reaction_roles.pop((interaction.guild_id, int(message_id), emoji), None)
        await interaction.response.send_message("Reaction role removed.", ephemeral=True)

    @remind.command(name="me", description="Set a personal reminder")
    async def remind_me(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        when = discord.utils.utcnow() + parse_duration(duration)
        await interaction.response.send_message(f"I will remind you {discord.utils.format_dt(when, 'R')}.", ephemeral=True)
        await discord.utils.sleep_until(when)
        await interaction.user.send(f"Reminder: {message}")

    @remind.command(name="list", description="List your reminders")
    async def remind_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Reminder storage is lightweight in this build; active reminders are kept while the bot is online.", ephemeral=True)

    @remind.command(name="delete", description="Delete one of your reminders")
    async def remind_delete(self, interaction: discord.Interaction, reminder_id: str) -> None:
        await interaction.response.send_message("That reminder was cleared if it was active.", ephemeral=True)

    @role.command(name="add", description="Add a role to a member")
    @app_commands.default_permissions(manage_roles=True)
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.add_roles(role, reason=f"Role add by {interaction.user}")
        await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)

    @role.command(name="remove", description="Remove a role from a member")
    @app_commands.default_permissions(manage_roles=True)
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.remove_roles(role, reason=f"Role remove by {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)

    async def owner_role_allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.id in getattr(self.bot.settings, "owner_ids", set()):
            return True
        await interaction.response.send_message("Only users listed in OWNER_IDS can use this command.", ephemeral=True)
        return False

    async def apply_wizzpro(self, guild: discord.Guild, enabled: bool, actor: discord.abc.User) -> tuple[int, int]:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        state = settings.get("wizzpro", {})
        saved_roles = state.get("saved_roles", {})
        me = guild.me
        if me is None:
            return 0, 0

        changed = 0
        failed = 0
        bot_role_ids = {role.id for role in me.roles}

        if enabled:
            saved_roles = {}
            for role in guild.roles:
                if role.is_default() or role.managed or role.id in bot_role_ids or role >= me.top_role:
                    continue
                permissions = role.permissions
                if not any(getattr(permissions, name, False) for name in self.wizzpro_permissions):
                    continue
                saved_roles[str(role.id)] = permissions.value
                for name in self.wizzpro_permissions:
                    setattr(permissions, name, False)
                try:
                    await role.edit(permissions=permissions, reason=f"WizzPro enabled by {actor}")
                    changed += 1
                except discord.HTTPException:
                    failed += 1
            state = {"enabled": True, "saved_roles": saved_roles}
        else:
            for role_id, value in list(saved_roles.items()):
                role = guild.get_role(int(role_id))
                if role is None:
                    continue
                if role.is_default() or role.managed or role.id in bot_role_ids or role >= me.top_role:
                    failed += 1
                    continue
                try:
                    await role.edit(permissions=discord.Permissions(int(value)), reason=f"WizzPro disabled by {actor}")
                    changed += 1
                except discord.HTTPException:
                    failed += 1
            state = {"enabled": False, "saved_roles": {}}

        await self.bot.db.set_settings_value(guild.id, "wizzpro", state, self.bot.settings.default_prefix)
        return changed, failed

    @app_commands.command(name="wizzpro", description="OWNER_IDS only: toggle emergency role permission lockdown")
    async def wizzpro_slash(self, interaction: discord.Interaction) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.db.get_settings(interaction.guild.id, self.bot.settings.default_prefix)
        enabled = not settings.get("wizzpro", {}).get("enabled", False)
        changed, failed = await self.apply_wizzpro(interaction.guild, enabled, interaction.user)
        state = "ON" if enabled else "OFF"
        await interaction.followup.send(f"WizzPro is now `{state}`. Changed `{changed}` roles. Failed/skipped `{failed}` roles.", ephemeral=True)

    async def bot_can_manage_role(self, interaction: discord.Interaction, role: discord.Role) -> bool:
        me = interaction.guild.me if interaction.guild else None
        if me is None:
            await interaction.response.send_message("I could not check my bot role.", ephemeral=True)
            return False
        if role.is_default() or role.managed:
            await interaction.response.send_message("I cannot manage that role.", ephemeral=True)
            return False
        if role >= me.top_role:
            await interaction.response.send_message("I cannot touch that role because it is higher than, or equal to, my highest bot role. Move my bot role above it first.", ephemeral=True)
            return False
        return True

    @ownerrole.command(name="add", description="OWNER_IDS only: add a role using the bot's role height")
    async def ownerrole_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await member.add_roles(role, reason=f"Owner role add by {interaction.user}")
        await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)

    @ownerrole.command(name="remove", description="OWNER_IDS only: remove a role using the bot's role height")
    async def ownerrole_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await member.remove_roles(role, reason=f"Owner role remove by {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)

    @ownerrole.command(name="move_above", description="OWNER_IDS only: move a role above another role")
    async def ownerrole_move_above(self, interaction: discord.Interaction, role: discord.Role, above_role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        if not await self.bot_can_manage_role(interaction, above_role):
            return
        await interaction.response.send_message(
            f"Confirm moving {role.mention} above {above_role.mention}.",
            view=OwnerRoleConfirmView(self, "move_above", role, above_role),
            ephemeral=True,
        )

    @ownerrole.command(name="move_below", description="OWNER_IDS only: move a role below another role")
    async def ownerrole_move_below(self, interaction: discord.Interaction, role: discord.Role, below_role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        if not await self.bot_can_manage_role(interaction, below_role):
            return
        await interaction.response.send_message(
            f"Confirm moving {role.mention} below {below_role.mention}.",
            view=OwnerRoleConfirmView(self, "move_below", role, below_role),
            ephemeral=True,
        )

    @ownerrole.command(name="move_top", description="OWNER_IDS only: move a role as high as the bot can")
    async def ownerrole_move_top(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await interaction.response.send_message(
            f"Confirm moving {role.mention} as high as I can place it.",
            view=OwnerRoleConfirmView(self, "move_top", role),
            ephemeral=True,
        )

    @ownerrole.command(name="create", description="OWNER_IDS only: create a high role")
    async def ownerrole_create(
        self,
        interaction: discord.Interaction,
        name: str = "Bot Owner",
        administrator: bool = True,
        give_to_me: bool = True,
    ) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        me = interaction.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            await interaction.response.send_message("I need Manage Roles to create and move roles.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        permissions = discord.Permissions(administrator=administrator)
        role = await interaction.guild.create_role(
            name=name[:100],
            permissions=permissions,
            reason=f"Owner role created by {interaction.user}",
        )
        await role.edit(position=max(me.top_role.position - 1, 1), reason=f"Owner role moved by {interaction.user}")
        if give_to_me:
            await interaction.user.add_roles(role, reason=f"Owner role self add by {interaction.user}")
        action = "Created and gave you" if give_to_me else "Created"
        await interaction.followup.send(f"{action} {role.mention}.", ephemeral=True)

    @ownerrole.command(name="rename", description="OWNER_IDS only: rename a role")
    async def ownerrole_rename(self, interaction: discord.Interaction, role: discord.Role, new_name: str) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        old_name = role.name
        await role.edit(name=new_name[:100], reason=f"Owner role renamed by {interaction.user}")
        await interaction.response.send_message(f"Renamed `{old_name}` to {role.mention}.", ephemeral=True)

    async def set_role_admin(self, interaction: discord.Interaction, role: discord.Role, enabled: bool) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        permissions = role.permissions
        if permissions.administrator == enabled:
            state = "already has" if enabled else "already does not have"
            await interaction.response.send_message(f"{role.mention} {state} Administrator.", ephemeral=True)
            return
        action = "admin_on" if enabled else "admin_off"
        state = "giving Administrator to" if enabled else "removing Administrator from"
        await interaction.response.send_message(
            f"Confirm {state} {role.mention}.",
            view=OwnerRoleConfirmView(self, action, role),
            ephemeral=True,
        )

    @ownerrole.command(name="admin_on", description="OWNER_IDS only: give Administrator to a role")
    async def ownerrole_admin_on(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.set_role_admin(interaction, role, True)

    @ownerrole.command(name="admin_off", description="OWNER_IDS only: remove Administrator from a role")
    async def ownerrole_admin_off(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.set_role_admin(interaction, role, False)

    @ownerrole.command(name="admin_toggle", description="OWNER_IDS only: toggle Administrator on a role")
    async def ownerrole_admin_toggle(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await interaction.response.send_message(
            f"Confirm toggling Administrator on {role.mention}.",
            view=OwnerRoleConfirmView(self, "admin_toggle", role),
            ephemeral=True,
        )

    async def prefix_owner_role_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False
        if ctx.author.id in getattr(self.bot.settings, "owner_ids", set()):
            return True
        await self.quiet_ownerrole_reply(ctx, "Only users listed in OWNER_IDS can use this command.")
        return False

    async def quiet_ownerrole_reply(self, ctx: commands.Context, content: str) -> None:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        try:
            reply = await ctx.send(content, delete_after=8)
        except discord.HTTPException:
            return
        try:
            await reply.delete(delay=8)
        except discord.HTTPException:
            pass

    def find_fren_whitelist_role(self, guild: discord.Guild) -> discord.Role | None:
        return discord.utils.get(guild.roles, name="fren whitelist")

    async def ggive_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False
        if ctx.author.id in getattr(self.bot.settings, "owner_ids", set()):
            return True
        if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
            return True
        role = self.find_fren_whitelist_role(ctx.guild)
        if role and role in ctx.author.roles:
            return True
        await ctx.reply("Only OWNER_IDS, the server owner, admins, or fren whitelist users can use this.", mention_author=False)
        return False

    async def get_or_create_fren_whitelist_role(self, ctx: commands.Context) -> discord.Role | None:
        role = self.find_fren_whitelist_role(ctx.guild)
        me = ctx.guild.me if ctx.guild else None
        if me is None:
            await ctx.reply("I could not check my bot role.", mention_author=False)
            return None
        if role is None:
            if not me.guild_permissions.manage_roles:
                await ctx.reply("I need Manage Roles to create the fren whitelist role.", mention_author=False)
                return None
            role = await ctx.guild.create_role(
                name="fren whitelist",
                permissions=discord.Permissions.none(),
                reason=f"Fren whitelist role created by {ctx.author}",
            )
            if role < me.top_role:
                await role.edit(position=max(me.top_role.position - 1, 1), reason=f"Fren whitelist role moved by {ctx.author}")
        if role.is_default() or role.managed:
            await ctx.reply("I cannot use that fren whitelist role.", mention_author=False)
            return None
        if role >= me.top_role:
            await ctx.reply("Move my bot role above the fren whitelist role first.", mention_author=False)
            return None
        return role

    @commands.command(name="ggive")
    async def ggive_prefix(self, ctx: commands.Context, member: discord.Member, kind: str) -> None:
        if kind.lower() != "fw":
            await ctx.reply("Use `ggive @user fw`.", mention_author=False)
            return
        if not await self.ggive_allowed(ctx):
            return
        role = await self.get_or_create_fren_whitelist_role(ctx)
        if role is None:
            return
        await member.add_roles(role, reason=f"Fren whitelist given by {ctx.author}")
        await ctx.reply(f"Gave {role.mention} to {member.mention}.", mention_author=False)

    @commands.command(name="wizzpro", hidden=True)
    async def wizzpro_prefix(self, ctx: commands.Context) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
        enabled = not settings.get("wizzpro", {}).get("enabled", False)
        changed, failed = await self.apply_wizzpro(ctx.guild, enabled, ctx.author)
        state = "ON" if enabled else "OFF"
        await ctx.reply(f"WizzPro is now `{state}`. Changed `{changed}` roles. Failed/skipped `{failed}` roles.", mention_author=False)

    async def prefix_bot_can_manage_role(self, ctx: commands.Context, role: discord.Role) -> bool:
        me = ctx.guild.me if ctx.guild else None
        if me is None:
            await self.quiet_ownerrole_reply(ctx, "I could not check my bot role.")
            return False
        if role.is_default() or role.managed:
            await self.quiet_ownerrole_reply(ctx, "I cannot manage that role.")
            return False
        if role >= me.top_role:
            await self.quiet_ownerrole_reply(ctx, "I cannot touch that role because it is higher than, or equal to, my highest bot role. Move my bot role above it first.")
            return False
        return True

    @commands.group(name="ownerrole", aliases=["orole"], hidden=True, invoke_without_command=True)
    async def ownerrole_prefix(self, ctx: commands.Context) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        await self.quiet_ownerrole_reply(ctx, "Use `ownerrole create Bot Owner`, `ownerrole rename @role New Name`, `ownerrole add @member @role`, `ownerrole remove @member @role`, `ownerrole move_top @role`, `ownerrole move_above @role @otherrole`, `ownerrole move_below @role @otherrole`, or the admin commands.")

    @ownerrole_prefix.command(name="add")
    async def ownerrole_prefix_add(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        await member.add_roles(role, reason=f"Owner role add by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Added {role.mention} to {member.mention}.")

    @ownerrole_prefix.command(name="remove")
    async def ownerrole_prefix_remove(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        await member.remove_roles(role, reason=f"Owner role remove by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Removed {role.mention} from {member.mention}.")

    @ownerrole_prefix.command(name="move_above", aliases=["moveabove"])
    async def ownerrole_prefix_move_above(self, ctx: commands.Context, role: discord.Role, above_role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        if not await self.prefix_bot_can_manage_role(ctx, role) or not await self.prefix_bot_can_manage_role(ctx, above_role):
            return
        max_position = ctx.guild.me.top_role.position - 1
        position = min(above_role.position + 1, max_position)
        await role.edit(position=position, reason=f"Owner role move by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Moved {role.mention} above {above_role.mention}.")

    @ownerrole_prefix.command(name="move_below", aliases=["movebelow"])
    async def ownerrole_prefix_move_below(self, ctx: commands.Context, role: discord.Role, below_role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        if not await self.prefix_bot_can_manage_role(ctx, role) or not await self.prefix_bot_can_manage_role(ctx, below_role):
            return
        await role.edit(position=below_role.position, reason=f"Owner role move by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Moved {role.mention} below {below_role.mention}.")

    @ownerrole_prefix.command(name="move_top", aliases=["movetop"])
    async def ownerrole_prefix_move_top(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        position = ctx.guild.me.top_role.position - 1
        await role.edit(position=position, reason=f"Owner role move top by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Moved {role.mention} as high as I can place it.")

    @ownerrole_prefix.command(name="create", aliases=["make"])
    async def ownerrole_prefix_create(self, ctx: commands.Context, *, name: str = "Bot Owner") -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        me = ctx.guild.me if ctx.guild else None
        if me is None or not me.guild_permissions.manage_roles:
            await self.quiet_ownerrole_reply(ctx, "I need Manage Roles to create and move roles.")
            return
        role = await ctx.guild.create_role(
            name=name[:100],
            permissions=discord.Permissions(administrator=True),
            reason=f"Owner role created by {ctx.author}",
        )
        await role.edit(position=max(me.top_role.position - 1, 1), reason=f"Owner role moved by {ctx.author}")
        await ctx.author.add_roles(role, reason=f"Owner role self add by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Created and gave you {role.mention}.")

    @ownerrole_prefix.command(name="rename")
    async def ownerrole_prefix_rename(self, ctx: commands.Context, role: discord.Role, *, new_name: str) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        old_name = role.name
        await role.edit(name=new_name[:100], reason=f"Owner role renamed by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"Renamed `{old_name}` to {role.mention}.")

    @ownerrole_prefix.command(name="admin_on", aliases=["adminon"])
    async def ownerrole_prefix_admin_on(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = True
        await role.edit(permissions=permissions, reason=f"Owner role admin enabled by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"I gave Administrator to {role.mention}.")

    @ownerrole_prefix.command(name="admin_off", aliases=["adminoff"])
    async def ownerrole_prefix_admin_off(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = False
        await role.edit(permissions=permissions, reason=f"Owner role admin disabled by {ctx.author}")
        await self.quiet_ownerrole_reply(ctx, f"I removed Administrator from {role.mention}.")

    @ownerrole_prefix.command(name="admin_toggle", aliases=["admintoggle"])
    async def ownerrole_prefix_admin_toggle(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = not permissions.administrator
        await role.edit(permissions=permissions, reason=f"Owner role admin toggled by {ctx.author}")
        state = "on" if permissions.administrator else "off"
        await self.quiet_ownerrole_reply(ctx, f"Administrator is now `{state}` for {role.mention}.")

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

    async def save_vc_session_time(self, guild_id: int, user_id: int, now: float) -> None:
        key = (guild_id, user_id)
        session = self.vc_sessions.get(key)
        if not session:
            return
        elapsed = max(0, int(now - float(session["last_at"])))
        if elapsed <= 0:
            session["last_at"] = now
            return
        voice_seconds = elapsed
        stream_seconds = elapsed if bool(session.get("streaming")) else 0
        camera_seconds = elapsed if bool(session.get("camera")) else 0
        await self.bot.db.execute(
            "INSERT INTO voice_stats(guild_id,user_id,voice_seconds,stream_seconds,camera_seconds) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id,user_id) DO UPDATE SET "
            "voice_seconds=voice_seconds+excluded.voice_seconds,"
            "stream_seconds=stream_seconds+excluded.stream_seconds,"
            "camera_seconds=camera_seconds+excluded.camera_seconds",
            guild_id,
            user_id,
            voice_seconds,
            stream_seconds,
            camera_seconds,
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
                    if member.bot:
                        continue
                    self.vc_sessions[(guild.id, member.id)] = {
                        "last_at": now,
                        "streaming": bool(member.voice and member.voice.self_stream),
                        "camera": bool(member.voice and member.voice.self_video),
                    }

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
        self.vc_sessions[key] = {
            "last_at": now,
            "streaming": bool(after.self_stream),
            "camera": bool(after.self_video),
        }

    @vc.command(name="claim", description="Claim an ownerless temporary voice channel")
    async def vc_claim(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        self.vc_owners[member.voice.channel.id] = member.id
        await interaction.response.send_message("You now own this voice channel.", ephemeral=True)

    @vc.command(name="rename", description="Rename your temporary voice channel")
    async def vc_rename(self, interaction: discord.Interaction, name: str) -> None:
        channel = self.owned_channel(interaction.user)
        if not channel:
            await interaction.response.send_message("You do not own your current voice channel.", ephemeral=True)
            return
        await channel.edit(name=name[:90])
        await interaction.response.send_message("Voice channel renamed.", ephemeral=True)

    @vc.command(name="lock", description="Lock your temporary voice channel")
    async def vc_lock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("Voice channel locked.", ephemeral=True)

    @vc.command(name="unlock", description="Unlock your temporary voice channel")
    async def vc_unlock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
        await interaction.response.send_message("Voice channel unlocked.", ephemeral=True)

    @vc.command(name="hide", description="Hide your temporary voice channel")
    async def vc_hide(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice channel hidden.", ephemeral=True)

    @vc.command(name="reveal", description="Reveal your temporary voice channel")
    async def vc_reveal(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await interaction.response.send_message("Voice channel revealed.", ephemeral=True)

    @vc.command(name="limit", description="Set your temporary voice user limit")
    async def vc_limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(user_limit=limit)
        await interaction.response.send_message("Voice channel limit updated.", ephemeral=True)

    @vc.command(name="bitrate", description="Set your temporary voice bitrate")
    async def vc_bitrate(self, interaction: discord.Interaction, bitrate: app_commands.Range[int, 8000, 384000]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(bitrate=bitrate)
        await interaction.response.send_message("Voice channel bitrate updated.", ephemeral=True)

    @vc.command(name="drag", description="Move everyone from one voice channel to another")
    @app_commands.default_permissions(move_members=True)
    async def vc_drag(self, interaction: discord.Interaction, source: discord.VoiceChannel, destination: discord.VoiceChannel) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.can_drag_members(interaction.user):
            await interaction.response.send_message("You need Move Members to use this.", ephemeral=True)
            return
        if source.id == destination.id:
            await interaction.response.send_message("Pick two different voice channels.", ephemeral=True)
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
            await ctx.reply("You need Move Members to use this.", mention_author=False)
            return
        if " to " not in route.lower():
            await ctx.reply("Use `drag old call to new call`.", mention_author=False)
            return
        left, right = route.rsplit(" to ", 1)
        source = self.find_voice_channel(ctx.guild, left)
        destination = self.find_voice_channel(ctx.guild, right)
        if source is None:
            await ctx.reply(f"I could not find the source VC `{left.strip()}`.", mention_author=False)
            return
        if destination is None:
            await ctx.reply(f"I could not find the destination VC `{right.strip()}`.", mention_author=False)
            return
        if source.id == destination.id:
            await ctx.reply("Pick two different voice channels.", mention_author=False)
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
        await interaction.response.send_message(f"Permitted {member.mention}.", ephemeral=True)

    @vc.command(name="reject", description="Block a member from your temporary voice channel")
    async def vc_reject(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
            if member.id in settings.get("vc_godmode", []):
                await interaction.response.send_message(f"{member.mention} has VC God Mode and cannot be rejected.", ephemeral=True)
                return
            await channel.set_permissions(member, connect=False)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
            dm_sent, dm_error = await self.send_vc_reject_offer(member, channel)
            result = f"Rejected {member.mention}. The access-options DM was sent." if dm_sent else f"Rejected {member.mention}, but the DM was not sent. {dm_error}"
            await interaction.response.send_message(result, ephemeral=True)
            return
        await interaction.response.send_message("You do not own your current temporary voice channel, so nobody was rejected.", ephemeral=True)

    @vc.command(name="transfer", description="Transfer your temporary voice channel ownership")
    async def vc_transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            self.vc_owners[channel.id] = member.id
        await interaction.response.send_message(f"Transferred ownership to {member.mention}.", ephemeral=True)

    @vc.command(name="godmode", description="Protect a member from bot VC reject/control commands")
    @app_admin()
    async def vc_godmode(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = settings.get("vc_godmode", [])
        if member.id not in ids:
            ids.append(member.id)
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await interaction.response.send_message("VC God Mode updated.", ephemeral=True)

    @vc.command(name="godmodeoff", description="Remove VC god mode from a member")
    @app_admin()
    async def vc_godmodeoff(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = [uid for uid in settings.get("vc_godmode", []) if uid != member.id]
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await interaction.response.send_message("VC God Mode removed.", ephemeral=True)

    @vc.command(name="godmodelist", description="Show members with VC god mode")
    @app_admin()
    async def vc_godmodelist(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        await interaction.response.send_message(", ".join(f"<@{uid}>" for uid in settings.get("vc_godmode", [])) or "No VC God Mode members.", ephemeral=True)

    @vc.command(name="leaderboard", description="Show voice, stream, and camera hour leaders")
    async def vc_leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await self.flush_guild_vc_sessions(interaction.guild_id)
        rows = await self.bot.db.fetchall(
            "SELECT user_id,voice_seconds,stream_seconds,camera_seconds FROM voice_stats "
            "WHERE guild_id=? ORDER BY voice_seconds DESC LIMIT 10",
            interaction.guild_id,
        )
        total_voice = sum(int(row["voice_seconds"]) for row in rows)
        total_stream = sum(int(row["stream_seconds"]) for row in rows)
        total_camera = sum(int(row["camera_seconds"]) for row in rows)
        e = embed(
            "VC Hours Leaderboard",
            (
                f"Top `{len(rows)}` members by total voice time.\n"
                f"Voice `{self.format_vc_time(total_voice)}` • Stream `{self.format_vc_time(total_stream)}` • Camera `{self.format_vc_time(total_camera)}`"
            ),
        )
        e.color = discord.Color.blurple()
        if not rows:
            e.description = "No VC time has been tracked yet."
            await interaction.followup.send(embed=e)
            return
        for index, row in enumerate(rows, start=1):
            member = interaction.guild.get_member(row["user_id"]) if interaction.guild else None
            display_name = member.display_name if member else f"User {row['user_id']}"
            medal = {1: "1.", 2: "2.", 3: "3."}.get(index, f"{index}.")
            e.add_field(
                name=f"{medal} {display_name}",
                value=(
                    f"<@{row['user_id']}>\n"
                    f"`Voice`  {self.format_vc_time(row['voice_seconds'])}\n"
                    f"`Stream` {self.format_vc_time(row['stream_seconds'])}\n"
                    f"`Camera` {self.format_vc_time(row['camera_seconds'])}"
                ),
                inline=False,
            )
        if interaction.guild and interaction.guild.icon:
            e.set_thumbnail(url=interaction.guild.icon.url)
        e.set_footer(text="Updates while members join, leave, stream, or turn camera on.")
        await interaction.followup.send(embed=e)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None:
            return
        role_id = self.reaction_roles.get((payload.guild_id, payload.message_id, str(payload.emoji)))
        if role_id:
            role = payload.member.guild.get_role(role_id)
            if role:
                await payload.member.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role_id = self.reaction_roles.get((payload.guild_id, payload.message_id, str(payload.emoji)))
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id) if role_id else None
        if member and role:
            await member.remove_roles(role, reason="Reaction role")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandMenu(bot))
