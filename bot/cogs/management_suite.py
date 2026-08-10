from __future__ import annotations

import io
import json
import time
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner, has_guild_permissions
from bot.core.utils import embed, style_embed, theme_color_from_data


FEATURES = (
    "antinuke", "automod", "backup", "birthday", "boost", "bug", "custom", "economy",
    "giveaway", "jtc", "levelrewards", "levels", "mod", "music", "notes", "quarantine",
    "remind", "security", "starboard", "store", "ticket", "verify", "voicexp", "welcome",
    "ownerrole", "wizzpro", "ai", "vouch",
)


class FeatureSelect(discord.ui.Select):
    def __init__(self, cog: "ManagementSuite", flags: dict[str, bool]) -> None:
        self.cog = cog
        options = [
            discord.SelectOption(label=name, value=name, description="On" if flags.get(name, True) else "Off")
            for name in FEATURES[:25]
        ]
        super().__init__(placeholder="Toggle a feature", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.settings(interaction.guild_id)
        flags = settings.get("feature_flags", {})
        current = flags.get(self.values[0], True)
        flags[self.values[0]] = not current
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.feature_embed(interaction.guild_id), view=FeaturePanel(self.cog, flags))


class FeaturePanel(discord.ui.View):
    def __init__(self, cog: "ManagementSuite", flags: dict[str, bool]) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(FeatureSelect(cog, flags))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and (interaction.user.guild_permissions.manage_guild or await configured_owner(interaction.client, interaction.user)):
            return True
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Missing Permission"), ephemeral=True)
        return False


class ConfirmActionView(discord.ui.View):
    def __init__(self, cog: "ManagementSuite", action: str, reason: str = "") -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.action = action
        self.reason = reason

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await configured_owner(self.cog.bot, interaction.user):
            return True
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
        return False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.action == "shutdown":
            await interaction.response.edit_message(embed=await self.cog.themed(interaction.guild_id, "Bot Shutting Down", self.reason[:500]), view=None)
            await self.cog.bot.close()
            return
        await interaction.response.edit_message(embed=await self.cog.themed(interaction.guild_id, "Confirmed"), view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=await self.cog.themed(interaction.guild_id, "Cancelled"), view=None)


class PanicPanel(discord.ui.View):
    def __init__(self, cog: "ManagementSuite") -> None:
        super().__init__(timeout=180)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await configured_owner(self.cog.bot, interaction.user):
            return True
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
        return False

    @discord.ui.button(label="Safe Mode", style=discord.ButtonStyle.danger)
    async def safe_mode(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        settings = await self.cog.settings(interaction.guild_id)
        flags = settings.get("feature_flags", {})
        for feature in ("backup", "security", "mod", "ownerrole", "wizzpro"):
            flags[feature] = False
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.cog.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Safe Mode On", "Risky command groups were disabled."), ephemeral=True)

    @discord.ui.button(label="Repair", style=discord.ButtonStyle.primary)
    async def repair(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        flags = (await self.cog.settings(interaction.guild_id)).get("feature_flags", {})
        for feature in FEATURES:
            flags.setdefault(feature, True)
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.cog.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Repair Complete", "Missing feature toggles were filled."), ephemeral=True)

    @discord.ui.button(label="Lock Text", style=discord.ButtonStyle.secondary)
    async def lock_text(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        locked = 0
        overwrite = discord.PermissionOverwrite(send_messages=False)
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason="Owner panic lock")
                locked += 1
            except discord.HTTPException:
                pass
        await interaction.followup.send(embed=await self.cog.themed(interaction.guild_id, "Panic Lock", f"Locked `{locked}` text channels."), ephemeral=True)

    @discord.ui.button(label="Doctor", style=discord.ButtonStyle.primary)
    async def doctor(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        failed = getattr(self.cog.bot, "failed_cogs", {})
        me = interaction.guild.me
        missing = []
        if me is not None:
            perms = me.guild_permissions
            for label, ok in (
                ("Manage Roles", perms.manage_roles),
                ("Manage Channels", perms.manage_channels),
                ("View Audit Log", perms.view_audit_log),
                ("Send Messages", perms.send_messages),
                ("Embed Links", perms.embed_links),
            ):
                if not ok:
                    missing.append(label)
        e = await self.cog.themed(interaction.guild_id, "Doctor Quick Check")
        e.add_field(name="Failed Add-ons", value="\n".join(f"`{name}`" for name in failed) or "None", inline=False)
        e.add_field(name="Missing Bot Perms", value="\n".join(missing) or "None", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="Backup", style=discord.ButtonStyle.success)
    async def backup(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=await self.cog.themed(interaction.guild_id, "Backup Reminder", "Use `/backup create` before big changes, then keep the generated code somewhere private."),
            ephemeral=True,
        )


class ManagementSuite(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    features = app_commands.Group(name="features", description="Turn bot features on or off")
    usagelogs = app_commands.Group(name="usagelogs", description="Command usage logs")
    cooldown = app_commands.Group(name="cooldown", description="Command cooldown manager")
    commandperms = app_commands.Group(name="commandperms", description="Lock commands to roles")
    profiles = app_commands.Group(name="profiles", description="Staff permission profiles")
    settingsio = app_commands.Group(name="settingsio", description="Import and export bot settings")
    backupdiff = app_commands.Group(name="backupdiff", description="Preview backup restore differences")
    botctl = app_commands.Group(name="botctl", description="OWNER_IDS only bot controls")
    data = app_commands.Group(name="data", description="Bot data cleanup tools")

    async def settings(self, guild_id: int) -> dict[str, Any]:
        return await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)

    async def themed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict[str, Any] = {}
        if guild_id is not None:
            settings = await self.settings(guild_id)
            theme = settings.get("theme", {})
            color = theme_color_from_data(theme, color)
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

    def slash_command_names(self) -> list[str]:
        names: list[str] = []
        for command in self.bot.tree.get_commands():
            names.append(command.qualified_name)
            if hasattr(command, "walk_commands"):
                names.extend(child.qualified_name for child in command.walk_commands())
        return names

    def find_command_conflicts(self) -> tuple[list[str], list[str]]:
        prefix_seen: dict[str, int] = {}
        slash_seen: dict[str, int] = {}
        for command in self.bot.walk_commands():
            prefix_seen[command.qualified_name] = prefix_seen.get(command.qualified_name, 0) + 1
            for alias in getattr(command, "aliases", []):
                prefix_seen[alias] = prefix_seen.get(alias, 0) + 1
        for name in self.slash_command_names():
            slash_seen[name] = slash_seen.get(name, 0) + 1
        prefix_dupes = sorted(name for name, count in prefix_seen.items() if count > 1)
        slash_dupes = sorted(name for name, count in slash_seen.items() if count > 1)
        return prefix_dupes, slash_dupes

    def scan_settings_ids(self, guild: discord.Guild, data: Any, path: str = "settings") -> list[str]:
        problems: list[str] = []
        if isinstance(data, dict):
            for key, value in data.items():
                next_path = f"{path}.{key}"
                if key.endswith("_id") and isinstance(value, int) and value:
                    found = guild.get_channel(value) or guild.get_role(value) or guild.get_member(value)
                    if found is None:
                        problems.append(f"`{next_path}` points to missing ID `{value}`")
                else:
                    problems.extend(self.scan_settings_ids(guild, value, next_path))
        elif isinstance(data, list):
            for index, value in enumerate(data[:100]):
                problems.extend(self.scan_settings_ids(guild, value, f"{path}[{index}]"))
        return problems[:25]

    async def simulate_member_command(self, guild_id: int, member: discord.Member, command_name: str) -> tuple[bool, list[str]]:
        settings = await self.settings(guild_id)
        name = command_name.strip().lstrip("/").lstrip(self.bot.settings.default_prefix).lower()
        root = name.split()[0] if name else ""
        reasons: list[str] = []
        allowed = True
        feature_flags = settings.get("feature_flags", {})
        if feature_flags.get(root) is False:
            allowed = False
            reasons.append(f"`{root}` is disabled in feature toggles.")
        if root in {"botctl", "ownerrole", "wizzpro"}:
            if await configured_owner(self.bot, member):
                reasons.append("User is in OWNER_IDS, so owner-only commands are allowed.")
            else:
                allowed = False
                reasons.append("This is OWNER_IDS only and the user is not in OWNER_IDS.")
        role_rules = settings.get("command_role_permissions", {})
        allowed_roles = role_rules.get(name) or role_rules.get(root)
        if allowed_roles:
            has_role = any(role.id in allowed_roles for role in member.roles)
            if has_role or member.guild_permissions.administrator:
                reasons.append("User passes this command's role lock.")
            else:
                allowed = False
                reasons.append("User does not have a role allowed by `/commandperms`.")
        if root in {"mod", "antinuke", "automod", "security", "features", "commandperms", "cooldown", "profiles", "settingsio", "data"}:
            if member.guild_permissions.manage_guild or member.guild_permissions.administrator or await configured_owner(self.bot, member):
                reasons.append("User has admin/manage-server style permissions for management commands.")
            else:
                allowed = False
                reasons.append("User is missing admin/manage-server style permissions.")
        prefix_command = self.bot.get_command(name)
        slash_names = {slash.lower() for slash in self.slash_command_names()}
        if prefix_command is None and name not in slash_names and root not in {slash.split()[0] for slash in slash_names}:
            reasons.append("I could not find an exact loaded command with that name.")
        if not reasons:
            reasons.append("No block found. They should be able to use it if Discord allows the command to appear.")
        return allowed, reasons

    async def feature_embed(self, guild_id: int) -> discord.Embed:
        settings = await self.settings(guild_id)
        flags = settings.get("feature_flags", {})
        e = await self.themed(guild_id, "Feature Toggles", "Use the menu to turn systems on/off.")
        lines = [f"`{'ON ' if flags.get(name, True) else 'OFF'}` **{name}**" for name in FEATURES]
        e.add_field(name="Features", value="\n".join(lines[:25])[:1024], inline=False)
        return e

    @app_commands.command(name="checklist", description="Show setup checklist")
    @app_admin()
    async def checklist(self, interaction: discord.Interaction) -> None:
        settings = await self.settings(interaction.guild_id)
        checks = [
            ("Owner IDs", bool(getattr(self.bot.settings, "owner_ids", set()))),
            ("Logs channel", bool(settings.get("logs_channel"))),
            ("Welcome channel", bool(settings.get("welcome", {}).get("channel_id"))),
            ("JTC lobby", bool(settings.get("jtc_templates"))),
            ("Ticket system", True),
            ("Anti-nuke", settings.get("antinuke_enabled", settings.get("antinuke_v2", {}).get("enabled", True)) is not False),
            ("Theme", bool(settings.get("theme"))),
            ("Backup webhook", bool(getattr(self.bot.settings, "backup_webhook_url", None))),
            ("Command logs", bool(settings.get("command_log_channel"))),
            ("Feature toggles", bool(settings.get("feature_flags"))),
        ]
        e = await self.themed(interaction.guild_id, "Setup Checklist")
        e.description = "\n".join(f"`{'OK' if ok else 'TODO'}` **{label}**" for label, ok in checks)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @features.command(name="panel", description="Open feature toggles")
    @app_admin()
    async def feature_panel(self, interaction: discord.Interaction) -> None:
        settings = await self.settings(interaction.guild_id)
        flags = settings.get("feature_flags", {})
        await interaction.response.send_message(embed=await self.feature_embed(interaction.guild_id), view=FeaturePanel(self, flags), ephemeral=True)

    @features.command(name="set", description="Turn one feature on/off")
    @app_admin()
    async def feature_set(self, interaction: discord.Interaction, feature: str, enabled: bool) -> None:
        settings = await self.settings(interaction.guild_id)
        flags = settings.get("feature_flags", {})
        flags[feature.lower()] = enabled
        await self.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Feature Updated"), ephemeral=True)

    @usagelogs.command(name="set", description="Set command usage log channel")
    @app_admin()
    async def usagelog_set(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "command_log_channel", channel.id if channel else 0, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Usage Log Updated"), ephemeral=True)

    @usagelogs.command(name="recent", description="Show recent command usage")
    @app_admin()
    async def usagelog_recent(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT actor_id,target_id,data,created_at FROM audit_events WHERE guild_id=? AND event='command_usage' ORDER BY id DESC LIMIT 10", interaction.guild_id)
        e = await self.themed(interaction.guild_id, "Recent Command Usage")
        lines = []
        for row in rows:
            data = json.loads(row["data"] or "{}")
            lines.append(f"<@{row['actor_id']}> `{data.get('command')}` in <#{row['target_id']}> - `{data.get('status')}`")
        e.description = "\n".join(lines)[:4000] or "No command usage recorded yet."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @cooldown.command(name="set", description="Set cooldown seconds for a prefix command/root")
    @app_admin()
    async def cooldown_set(self, interaction: discord.Interaction, command: str, seconds: app_commands.Range[int, 0, 86400]) -> None:
        settings = await self.settings(interaction.guild_id)
        cooldowns = settings.get("command_cooldowns", {})
        cooldowns[command.lower()] = int(seconds)
        await self.bot.db.set_settings_value(interaction.guild_id, "command_cooldowns", cooldowns, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Cooldown Updated"), ephemeral=True)

    @cooldown.command(name="list", description="List command cooldowns")
    @app_admin()
    async def cooldown_list(self, interaction: discord.Interaction) -> None:
        cooldowns = (await self.settings(interaction.guild_id)).get("command_cooldowns", {})
        e = await self.themed(interaction.guild_id, "Command Cooldowns")
        e.description = "\n".join(f"`{cmd}` - `{sec}s`" for cmd, sec in cooldowns.items()) or "No cooldowns set."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commandperms.command(name="set", description="Allow only a role to use a command/root")
    @app_admin()
    async def commandperms_set(self, interaction: discord.Interaction, command: str, role: discord.Role) -> None:
        settings = await self.settings(interaction.guild_id)
        rules = settings.get("command_role_permissions", {})
        roles = rules.setdefault(command.lower(), [])
        if role.id not in roles:
            roles.append(role.id)
        await self.bot.db.set_settings_value(interaction.guild_id, "command_role_permissions", rules, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Command Permission Updated"), ephemeral=True)

    @commandperms.command(name="clear", description="Clear role lock for a command/root")
    @app_admin()
    async def commandperms_clear(self, interaction: discord.Interaction, command: str) -> None:
        settings = await self.settings(interaction.guild_id)
        rules = settings.get("command_role_permissions", {})
        rules.pop(command.lower(), None)
        await self.bot.db.set_settings_value(interaction.guild_id, "command_role_permissions", rules, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Command Permission Cleared"), ephemeral=True)

    @profiles.command(name="create", description="Create a staff profile")
    @app_admin()
    async def profile_create(self, interaction: discord.Interaction, name: str, role: discord.Role) -> None:
        settings = await self.settings(interaction.guild_id)
        profiles = settings.get("staff_profiles", {})
        profiles[name.lower()] = {"role_id": role.id, "commands": []}
        await self.bot.db.set_settings_value(interaction.guild_id, "staff_profiles", profiles, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Profile Created"), ephemeral=True)

    @profiles.command(name="allow", description="Allow a command for a profile")
    @app_admin()
    async def profile_allow(self, interaction: discord.Interaction, profile: str, command: str) -> None:
        settings = await self.settings(interaction.guild_id)
        profiles = settings.get("staff_profiles", {})
        data = profiles.setdefault(profile.lower(), {"role_id": 0, "commands": []})
        if command.lower() not in data["commands"]:
            data["commands"].append(command.lower())
        role_id = data.get("role_id")
        if role_id:
            rules = settings.get("command_role_permissions", {})
            roles = rules.setdefault(command.lower(), [])
            if role_id not in roles:
                roles.append(role_id)
            await self.bot.db.set_settings_value(interaction.guild_id, "command_role_permissions", rules, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(interaction.guild_id, "staff_profiles", profiles, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Profile Updated"), ephemeral=True)

    @profiles.command(name="list", description="List staff profiles")
    @app_admin()
    async def profile_list(self, interaction: discord.Interaction) -> None:
        profiles = (await self.settings(interaction.guild_id)).get("staff_profiles", {})
        e = await self.themed(interaction.guild_id, "Staff Profiles")
        e.description = "\n".join(f"`{name}` - <@&{data.get('role_id')}> - `{len(data.get('commands', []))}` commands" for name, data in profiles.items()) or "No profiles set."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @settingsio.command(name="export", description="Export bot settings as JSON")
    @app_admin()
    async def settings_export(self, interaction: discord.Interaction) -> None:
        settings = await self.settings(interaction.guild_id)
        data = json.dumps(settings, indent=2).encode("utf-8")
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Settings Exported"), file=discord.File(io.BytesIO(data), filename="ainbot-settings.json"), ephemeral=True)

    @settingsio.command(name="import", description="Import bot settings JSON text")
    @app_admin()
    async def settings_import(self, interaction: discord.Interaction, json_text: str) -> None:
        try:
            data = json.loads(json_text)
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Bad JSON"), ephemeral=True)
            return
        prefix = str(data.pop("prefix", self.bot.settings.default_prefix))[:12]
        await self.bot.db.set_prefix(interaction.guild_id, prefix, self.bot.settings.default_prefix)
        for key, value in data.items():
            await self.bot.db.set_settings_value(interaction.guild_id, key, value, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Settings Imported"), ephemeral=True)

    @settingsio.command(name="check", description="Check settings JSON before importing")
    @app_admin()
    async def settings_check(self, interaction: discord.Interaction, json_text: str) -> None:
        try:
            data = json.loads(json_text)
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Bad JSON"), ephemeral=True)
            return
        problems = self.scan_settings_ids(interaction.guild, data)
        e = await self.themed(interaction.guild_id, "Import Check")
        e.description = "\n".join(problems) or "Looks okay. I did not find missing role/channel/member IDs."
        e.add_field(name="Settings Found", value=f"`{len(data)}` top-level keys", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @backupdiff.command(name="preview", description="Preview what a backup restore would add")
    @app_admin()
    async def backupdiff_preview(self, interaction: discord.Interaction, code: str) -> None:
        row = await self.bot.db.fetchrow("SELECT snapshot FROM backup_codes WHERE code=?", code.upper())
        if row is None:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Backup Not Found"), ephemeral=True)
            return
        data = json.loads(row["snapshot"])
        current_roles = {role.name for role in interaction.guild.roles}
        current_channels = {channel.name for channel in interaction.guild.channels}
        new_roles = [role["name"] for role in data.get("roles", []) if role["name"] not in current_roles]
        new_channels = [channel["name"] for channel in data.get("channels", []) if channel["name"] not in current_channels]
        e = await self.themed(interaction.guild_id, "Backup Diff Preview")
        e.add_field(name="Roles To Add", value="\n".join(f"`{name}`" for name in new_roles[:20]) or "None", inline=False)
        e.add_field(name="Channels To Add", value="\n".join(f"`{name}`" for name in new_channels[:20]) or "None", inline=False)
        e.add_field(name="Settings Included", value=f"`{len(data.get('settings', {}))}` settings", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="status", description="Show bot status panel")
    async def status_panel(self, interaction: discord.Interaction) -> None:
        uptime = int((discord.utils.utcnow() - self.bot.started_at).total_seconds())
        e = await self.themed(interaction.guild_id, "Bot Status")
        e.add_field(name="Ping", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)
        e.add_field(name="Uptime", value=f"`{uptime // 3600}h {(uptime % 3600) // 60}m`", inline=True)
        e.add_field(name="Servers", value=f"`{len(self.bot.guilds)}`", inline=True)
        e.add_field(name="Slash Groups", value=f"`{len(self.bot.tree.get_commands())}`", inline=True)
        e.add_field(name="Music", value="On" if getattr(self.bot.settings, "enable_music", True) else "Off", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="repair", description="Try to fix common setup problems")
    @app_admin()
    async def repair(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.settings(interaction.guild_id)
        fixed = []
        if self.bot.settings.default_prefix and settings.get("prefix") != self.bot.settings.default_prefix:
            await self.bot.db.set_prefix(interaction.guild_id, self.bot.settings.default_prefix, self.bot.settings.default_prefix)
            fixed.append("Reset prefix to Railway default.")
        flags = settings.get("feature_flags", {})
        for feature in FEATURES:
            flags.setdefault(feature, True)
        await self.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.bot.settings.default_prefix)
        fixed.append("Filled missing feature toggles.")
        if isinstance(interaction.channel, discord.TextChannel):
            perms = interaction.channel.permissions_for(interaction.guild.me)
            if not (perms.send_messages and perms.embed_links):
                fixed.append("Could not fix channel perms automatically; give Send Messages and Embed Links.")
        await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Repair Complete", "\n".join(fixed) or "Nothing needed fixing."), ephemeral=True)

    @app_commands.command(name="simulate", description="Check whether a member can use a command")
    @app_admin()
    async def simulate(self, interaction: discord.Interaction, member: discord.Member, commandname: str) -> None:
        allowed, reasons = await self.simulate_member_command(interaction.guild_id, member, commandname)
        e = await self.themed(interaction.guild_id, "Permission Simulation", "\n".join(reasons)[:3500])
        e.add_field(name="User", value=member.mention, inline=True)
        e.add_field(name="Command", value=f"`{commandname}`", inline=True)
        e.add_field(name="Result", value="Allowed" if allowed else "Blocked", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="version", description="Show the latest bot update notes")
    async def version(self, interaction: discord.Interaction) -> None:
        settings = await self.settings(interaction.guild_id)
        changelog = settings.get("bot_changelog", {})
        name = changelog.get("name", "Safety And Polish Update")
        notes = changelog.get("notes") or "Crash recovery, panic panel, command conflict checks, data cleanup, import checker, and safer shutdown confirmations."
        e = await self.themed(interaction.guild_id, str(name)[:80], str(notes)[:3500])
        e.add_field(name="Slash Commands", value=f"`{len(self.slash_command_names())}` loaded", inline=True)
        e.add_field(name="Prefix Commands", value=f"`{len(list(self.bot.walk_commands()))}` loaded", inline=True)
        failed = getattr(self.bot, "failed_cogs", {})
        e.add_field(name="Load Issues", value=f"`{len(failed)}`" if failed else "`0`", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="updates", description="Show recent AinBot updates with dates and added features")
    async def updates(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT released_on,title,notes FROM bot_updates ORDER BY released_on DESC,id DESC LIMIT 10")
        e = await self.themed(interaction.guild_id, "Recent AinBot Updates", "Newest updates are shown first.")
        for row in rows:
            e.add_field(name=f"{row['released_on']} — {row['title']}", value=str(row["notes"])[:1024], inline=False)
        if not rows:
            e.description = "No update history has been published yet."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @botctl.command(name="panic", description="OWNER_IDS only: open emergency bot controls")
    async def botctl_panic(self, interaction: discord.Interaction) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=await self.themed(interaction.guild_id, "Owner Panic Panel", "Emergency controls for safe mode, lockdown, shutdown, repair, doctor, and backup reminders."),
            view=PanicPanel(self),
            ephemeral=True,
        )

    @botctl.command(name="conflicts", description="OWNER_IDS only: scan command conflicts and failed cogs")
    async def botctl_conflicts(self, interaction: discord.Interaction) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
            return
        prefix_dupes, slash_dupes = self.find_command_conflicts()
        failed = getattr(self.bot, "failed_cogs", {})
        e = await self.themed(interaction.guild_id, "Command Health Scan")
        e.add_field(name="Prefix Conflicts", value="\n".join(f"`{name}`" for name in prefix_dupes[:15]) or "None", inline=False)
        e.add_field(name="Slash Conflicts", value="\n".join(f"`{name}`" for name in slash_dupes[:15]) or "None", inline=False)
        e.add_field(name="Failed Add-ons", value="\n".join(f"`{name}` - {reason}" for name, reason in list(failed.items())[:8]) or "None", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @botctl.command(name="safemode", description="OWNER_IDS only: disable risky command groups")
    async def botctl_safemode(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
            return
        settings = await self.settings(interaction.guild_id)
        flags = settings.get("feature_flags", {})
        risky = ("backup", "security", "mod", "ownerrole", "wizzpro")
        for feature in risky:
            flags[feature] = not enabled
        await self.bot.db.set_settings_value(interaction.guild_id, "feature_flags", flags, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Safe Mode Updated", "Risky groups are now disabled." if enabled else "Risky groups are back on."), ephemeral=True)

    @botctl.command(name="cleanup", description="OWNER_IDS only: clean old bot data")
    async def botctl_cleanup(self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 365] = 30) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
            return
        cutoff = f"-{int(days)} days"
        await self.bot.db.execute("DELETE FROM audit_events WHERE guild_id=? AND created_at < datetime('now', ?)", interaction.guild_id, cutoff)
        await self.bot.db.execute("DELETE FROM temp_actions WHERE guild_id=? AND expires_at < ?", interaction.guild_id, time.time())
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Cleanup Complete", f"Removed old logs older than `{days}` days and expired temp actions."), ephemeral=True)

    @data.command(name="cleanup", description="Clean old logs, command usage, reminders, and expired temp actions")
    @app_admin()
    async def data_cleanup(self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 365] = 30) -> None:
        cutoff = f"-{int(days)} days"
        settings = await self.settings(interaction.guild_id)
        reminders = settings.get("button_reminders", [])
        now = time.time()
        remaining = [item for item in reminders if float(item.get("at", 0) or 0) > now]
        await self.bot.db.set_settings_value(interaction.guild_id, "button_reminders", remaining[-200:], self.bot.settings.default_prefix)
        await self.bot.db.execute("DELETE FROM audit_events WHERE guild_id=? AND created_at < datetime('now', ?)", interaction.guild_id, cutoff)
        await self.bot.db.execute("DELETE FROM temp_actions WHERE guild_id=? AND expires_at < ?", interaction.guild_id, now)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Data Cleanup", f"Cleaned old logs/command usage older than `{days}` days, expired temp actions, and expired reminders."), ephemeral=True)

    @botctl.command(name="changelog", description="OWNER_IDS only: set what /version shows")
    async def botctl_changelog(self, interaction: discord.Interaction, name: str, notes: str) -> None:
        if not await configured_owner(self.bot, interaction.user):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner Only"), ephemeral=True)
            return
        await self.bot.db.set_settings_value(interaction.guild_id, "bot_changelog", {"name": name[:80], "notes": notes[:3500]}, self.bot.settings.default_prefix)
        released_on = discord.utils.utcnow().date().isoformat()
        update_key = f"custom-{interaction.id}"
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO bot_updates(update_key,released_on,title,notes,created_by) VALUES(?,?,?,?,?)",
            update_key,
            released_on,
            name[:80],
            notes[:3500],
            interaction.user.id,
        )
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Changelog Updated"), ephemeral=True)

    @app_commands.command(name="ainsd", description="OWNER_IDS only: shut down every AinBot service")
    async def ainsd(self, interaction: discord.Interaction, reason: str = "Owner requested shutdown") -> None:
        owner_ids = getattr(self.bot.settings, "owner_ids", set())
        if interaction.user.id not in owner_ids:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Owner ID Only", "Your Discord ID is not saved in AinBot's Owner IDs list."), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=await self.themed(interaction.guild_id, "Confirm AinBot Shutdown", "This disconnects the bot, stops background tasks, music helpers and the dashboard process. Press Confirm to continue."),
            view=ConfirmActionView(self, "shutdown", reason),
            ephemeral=True,
        )

    @commands.command(name="checklist")
    @has_guild_permissions(manage_guild=True)
    async def prefix_checklist(self, ctx: commands.Context) -> None:
        fake = await self.themed(ctx.guild.id, "Setup Checklist", "Use `/checklist` for the full private checklist.")
        await ctx.reply(embed=fake, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ManagementSuite(bot))
