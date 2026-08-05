from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed, style_embed


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
            color = discord.Color(int(theme.get("color", color.value)))
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

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
