from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed, style_embed, theme_color_from_data


DANGEROUS_PERMS = (
    "administrator",
    "ban_members",
    "kick_members",
    "manage_roles",
    "manage_channels",
    "manage_guild",
    "manage_webhooks",
    "moderate_members",
    "view_audit_log",
)


class SetupTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    setup = app_commands.Group(name="setup", description="Fast bot setup tools")
    dashboard = app_commands.Group(name="dashboard", description="Clean setup/status dashboards")
    scan = app_commands.Group(name="scan", description="Server scan tools")

    async def themed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict = {}
        if guild_id is not None:
            settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
            theme = settings.get("theme", {})
            color = theme_color_from_data(theme, color)
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        self.bot.log.exception("Setup command failed", exc_info=error)
        message = f"Setup stopped: `{type(error).__name__}`. Check the bot's role permissions and Railway logs."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    @setup.command(name="wizard", description="Set the main channels/categories the bot should use")
    @app_admin()
    async def setup_wizard(
        self,
        interaction: discord.Interaction,
        logs: discord.TextChannel | None = None,
        welcome: discord.TextChannel | None = None,
        tickets: discord.CategoryChannel | None = None,
        backup: discord.TextChannel | None = None,
        prefix: str | None = None,
    ) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        setup_data = settings.get("setup", {})
        if logs:
            await self.bot.db.set_settings_value(interaction.guild_id, "logs_channel", logs.id, self.bot.settings.default_prefix)
            setup_data["logs_channel"] = logs.id
        if welcome:
            welcome_data = settings.get("welcome", {})
            welcome_data["channel_id"] = welcome.id
            await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome_data, self.bot.settings.default_prefix)
            setup_data["welcome_channel"] = welcome.id
        if tickets:
            setup_data["ticket_category"] = tickets.id
        if backup:
            setup_data["backup_channel"] = backup.id
            await self.bot.db.set_settings_value(interaction.guild_id, "sync_announce_channel", backup.id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(interaction.guild_id, "setup", setup_data, self.bot.settings.default_prefix)
        if prefix:
            await self.bot.db.set_prefix(interaction.guild_id, prefix[:12], self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Setup Saved")
        e.add_field(name="Logs", value=logs.mention if logs else "No change", inline=True)
        e.add_field(name="Welcome", value=welcome.mention if welcome else "No change", inline=True)
        e.add_field(name="Tickets", value=tickets.name if tickets else "No change", inline=True)
        e.add_field(name="Backup/Updates", value=backup.mention if backup else "No change", inline=True)
        e.add_field(name="Prefix", value=f"`{prefix[:12]}`" if prefix else "No change", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @setup.command(name="jtc", description="Quickly configure join-to-create")
    @app_admin()
    async def setup_jtc(
        self,
        interaction: discord.Interaction,
        lobby: discord.VoiceChannel,
        output_category: discord.CategoryChannel | None = None,
        name: str = "{user}'s room",
        user_limit: app_commands.Range[int, 0, 99] = 0,
    ) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        templates[str(lobby.id)] = {
            "name": name,
            "user_limit": int(user_limit),
            "category_id": output_category.id if output_category else None,
        }
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", templates, self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "JTC Setup Saved")
        e.add_field(name="Lobby", value=lobby.mention, inline=True)
        e.add_field(name="Temp Category", value=output_category.name if output_category else "Same as lobby", inline=True)
        e.add_field(name="Name", value=f"`{name}`", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @setup.command(name="bot_community", description="Build a compact AinBot promotion and support server")
    async def setup_bot_community(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Run this command inside a Discord server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and not await self.bot.is_owner(interaction.user):
            await interaction.followup.send("Only a server administrator or configured bot owner can build the community server.", ephemeral=True)
            return
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
            await interaction.followup.send("I need Manage Channels and Manage Roles before I can build the server.", ephemeral=True)
            return

        role_specs = [
            ("AinBot Owner", discord.Permissions(administrator=True)),
            ("Bot Developer", discord.Permissions(manage_guild=True, manage_channels=True, manage_roles=True, view_audit_log=True)),
            ("Support Lead", discord.Permissions(manage_messages=True, moderate_members=True, view_audit_log=True)),
            ("Support Team", discord.Permissions(manage_messages=True)),
            ("Moderator", discord.Permissions(manage_messages=True, moderate_members=True, kick_members=True)),
            ("Partner", discord.Permissions.none()),
            ("Premium", discord.Permissions.none()),
            ("Verified", discord.Permissions.none()),
            ("Bots", discord.Permissions.none()),
            ("Muted", discord.Permissions.none()),
        ]
        roles: dict[str, discord.Role] = {}
        for name, permissions in role_specs:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                role = await guild.create_role(name=name, permissions=permissions, reason="AinBot community setup")
            roles[name] = role

        everyone = guild.default_role
        staff_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            roles["AinBot Owner"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Bot Developer"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Lead"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Team"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Moderator"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        premium_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            roles["Premium"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["AinBot Owner"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Team"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        async def category(name: str, overwrites: dict | None = None) -> discord.CategoryChannel:
            found = discord.utils.get(guild.categories, name=name)
            return found or await guild.create_category(name, overwrites=overwrites, reason="AinBot community setup")

        async def text_channel(cat: discord.CategoryChannel, name: str, topic: str, read_only: bool = False) -> discord.TextChannel:
            found = discord.utils.get(cat.text_channels, name=name)
            if found:
                return found
            overwrites = None
            if read_only:
                overwrites = {everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False), me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
            return await guild.create_text_channel(name, category=cat, topic=topic, overwrites=overwrites, reason="AinBot community setup")

        start = await category("START HERE")
        bot_hub = await category("AINBOT")
        community = await category("COMMUNITY")
        support = await category("SUPPORT")
        premium = await category("PREMIUM", premium_overwrites)
        staff = await category("STAFF", staff_overwrites)
        voice = await category("VOICE")

        welcome = await text_channel(start, "welcome", "Start here for AinBot information and community access.", True)
        rules = await text_channel(start, "rules", "Community rules and Discord requirements.", True)
        verify = await text_channel(start, "verify", "Account verification and member access.", True)
        announcements = await text_channel(bot_hub, "announcements", "Official AinBot announcements.", True)
        updates = await text_channel(bot_hub, "updates", "AinBot updates, fixes, and release notes.", True)
        status = await text_channel(bot_hub, "status", "Live service and incident updates.", True)
        commands_channel = await text_channel(bot_hub, "commands", "Command list and usage information.", True)
        invite = await text_channel(bot_hub, "invite-ainbot", "Invite and authorization links for AinBot.", True)
        general = await text_channel(community, "general", "Main AinBot community chat.")
        showcase = await text_channel(community, "showcase", "Show server setups, themes, and AinBot results.")
        suggestions = await text_channel(community, "suggestions", "Suggest new AinBot features and improvements.")
        faq = await text_channel(support, "faq", "Common setup and troubleshooting answers.", True)
        tickets = await text_channel(support, "open-a-ticket", "Open a private support ticket here.", True)
        premium_chat = await text_channel(premium, "premium-chat", "Private chat for AinBot Premium members.")
        premium_support = await text_channel(premium, "premium-support", "Priority support for Premium members.")
        staff_chat = await text_channel(staff, "staff-chat", "Private staff coordination.")
        staff_logs = await text_channel(staff, "bot-logs", "Private AinBot and moderation logs.")
        payment_logs = await text_channel(staff, "payment-logs", "Private purchase and fulfillment notices.")

        if discord.utils.get(voice.voice_channels, name="Community VC") is None:
            await guild.create_voice_channel("Community VC", category=voice, reason="AinBot community setup")
        if discord.utils.get(voice.voice_channels, name="Support Waiting") is None:
            await guild.create_voice_channel("Support Waiting", category=voice, reason="AinBot community setup")
        if discord.utils.get(voice.voice_channels, name="Premium VC") is None:
            await guild.create_voice_channel("Premium VC", category=premium, overwrites=premium_overwrites, reason="AinBot community setup")

        await self.bot.db.set_settings_value(guild.id, "logs_channel", staff_logs.id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "welcome", {"channel_id": welcome.id, "message": "Welcome {mention} to the official AinBot community."}, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "setup", {"logs_channel": staff_logs.id, "welcome_channel": welcome.id, "ticket_category": support.id, "backup_channel": updates.id, "payment_logs_channel": payment_logs.id}, self.bot.settings.default_prefix)

        await welcome.send(embed=await self.themed(guild.id, "Welcome to AinBot", "Get updates, support, premium access, setup help, and everything you need to run AinBot in your server."))
        await rules.send(embed=await self.themed(guild.id, "Community Rules", "1. Respect members and staff.\n2. No scams, credential requests, raids, or abuse.\n3. Use support tickets for private help.\n4. Keep payment information private.\n5. Follow Discord's Terms of Service."))
        await interaction.followup.send(embed=await self.themed(guild.id, "AinBot Community Server Ready", f"Created the compact promotion and support layout.\n\nStart in {welcome.mention}. Post your ticket panel in {tickets.mention}, verification panel in {verify.mention}, and command dashboard in {commands_channel.mention}."), ephemeral=True)

    @dashboard.command(name="overview", description="Show all major bot modules and setup status")
    @app_admin()
    async def dashboard_overview(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Bot Dashboard")
        e.add_field(name="Prefix", value=f"`{settings.get('prefix', self.bot.settings.default_prefix)}`", inline=True)
        e.add_field(name="Anti-Nuke", value="On" if settings.get("antinuke_enabled", settings.get("antinuke_v2", {}).get("enabled", True)) else "Off", inline=True)
        e.add_field(name="Music", value="On" if getattr(self.bot.settings, "enable_music", True) else "Off", inline=True)
        e.add_field(name="JTC Lobbies", value=f"`{len(settings.get('jtc_templates', {}))}`", inline=True)
        e.add_field(name="Welcome", value="Set" if settings.get("welcome", {}).get("channel_id") else "Not set", inline=True)
        e.add_field(name="Logs", value=f"<#{settings.get('logs_channel')}>" if settings.get("logs_channel") else "Not set", inline=True)
        e.add_field(name="Theme", value="Set" if settings.get("theme") else "Default", inline=True)
        e.add_field(name="Backup", value="Webhook set" if getattr(self.bot.settings, "backup_webhook_url", None) else "No webhook", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @dashboard.command(name="post", description="Post a clean public bot dashboard")
    @app_admin()
    async def dashboard_post(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Server Bot Dashboard", "Current bot systems and quick status.")
        e.add_field(name="Commands", value=f"`{len(self.bot.tree.get_commands())}` slash groups loaded", inline=True)
        e.add_field(name="Prefix", value=f"`{settings.get('prefix', self.bot.settings.default_prefix)}`", inline=True)
        e.add_field(name="Status", value="Online", inline=True)
        e.add_field(name="Useful Checks", value="Run `/doctor` if anything stops working.", inline=False)
        await target.send(embed=e)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Dashboard Posted"), ephemeral=True)

    @scan.command(name="perms", description="Scan dangerous roles and members")
    @app_admin()
    async def scan_perms(self, interaction: discord.Interaction) -> None:
        dangerous_roles = []
        for role in sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True):
            hits = [name for name in DANGEROUS_PERMS if getattr(role.permissions, name)]
            if hits and not role.is_default():
                dangerous_roles.append(f"{role.mention} - `{', '.join(hits[:4])}`")
        dangerous_members = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            hits = [name for name in DANGEROUS_PERMS if getattr(member.guild_permissions, name)]
            if hits:
                dangerous_members.append(f"{member.mention} - `{', '.join(hits[:4])}`")
        e = await self.themed(interaction.guild_id, "Permission Scan")
        e.add_field(name="Dangerous Roles", value="\n".join(dangerous_roles[:15])[:1024] or "None found.", inline=False)
        e.add_field(name="Dangerous Members", value="\n".join(dangerous_members[:15])[:1024] or "None found.", inline=False)
        e.set_footer(text="Only the first 15 of each list are shown.")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="checkperms", description="Check what permissions the bot is missing in a channel")
    @app_admin()
    async def checkperms(self, interaction: discord.Interaction, channel: discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel | None = None) -> None:
        target = channel or interaction.channel
        me = interaction.guild.me
        perms = target.permissions_for(me)
        required = {
            "view_channel": "View Channel",
            "send_messages": "Send Messages",
            "embed_links": "Embed Links",
            "manage_messages": "Manage Messages",
            "manage_channels": "Manage Channels",
            "connect": "Connect",
            "speak": "Speak",
            "move_members": "Move Members",
        }
        lines = []
        for attr, label in required.items():
            value = getattr(perms, attr, False)
            lines.append(f"`{'OK' if value else 'FIX'}` **{label}**")
        e = await self.themed(interaction.guild_id, "Channel Permission Check", f"Target: {target.mention if hasattr(target, 'mention') else target.name}")
        e.add_field(name="Needed Permissions", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.command(name="setupwizard", aliases=["setup"])
    @has_guild_permissions(manage_guild=True)
    async def prefix_setupwizard(self, ctx: commands.Context) -> None:
        e = await self.themed(ctx.guild.id, "Setup Wizard", "Use `/setup wizard` for the clickable setup form.\nUse `/setup jtc` for join-to-create setup.\nUse `/dashboard overview` to check the bot.")
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="checkperms")
    @has_guild_permissions(manage_guild=True)
    async def prefix_checkperms(self, ctx: commands.Context) -> None:
        me = ctx.guild.me
        perms = ctx.channel.permissions_for(me)
        lines = [
            f"`{'OK' if perms.view_channel else 'FIX'}` **View Channel**",
            f"`{'OK' if perms.send_messages else 'FIX'}` **Send Messages**",
            f"`{'OK' if perms.embed_links else 'FIX'}` **Embed Links**",
            f"`{'OK' if perms.manage_messages else 'FIX'}` **Manage Messages**",
        ]
        e = await self.themed(ctx.guild.id, "Channel Permission Check")
        e.add_field(name="Needed Permissions", value="\n".join(lines), inline=False)
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupTools(bot))
