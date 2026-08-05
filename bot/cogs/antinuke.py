from __future__ import annotations

import datetime as dt
import json
import time
from collections import defaultdict, deque
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner
from bot.core.utils import embed


PUNISHMENTS = {
    "strip_roles": "Strip Roles",
    "ban": "Ban",
    "kick": "Kick",
    "timeout": "Timeout",
    "log_only": "Log Only",
    "ignore": "Ignore",
}

PROTECTIONS: dict[str, dict[str, Any]] = {
    "channel_delete": {"label": "Channel Delete", "audit": discord.AuditLogAction.channel_delete, "threshold": 2, "seconds": 20},
    "channel_create": {"label": "Channel Create Spam", "audit": discord.AuditLogAction.channel_create, "threshold": 4, "seconds": 30},
    "channel_update": {"label": "Channel Update", "audit": discord.AuditLogAction.channel_update, "threshold": 4, "seconds": 30},
    "role_delete": {"label": "Role Delete", "audit": discord.AuditLogAction.role_delete, "threshold": 2, "seconds": 20},
    "role_create": {"label": "Role Create Spam", "audit": discord.AuditLogAction.role_create, "threshold": 4, "seconds": 30},
    "role_update": {"label": "Role Permission Abuse", "audit": discord.AuditLogAction.role_update, "threshold": 3, "seconds": 30},
    "webhook_create": {"label": "Webhook Create", "audit": discord.AuditLogAction.webhook_create, "threshold": 2, "seconds": 30},
    "webhook_delete": {"label": "Webhook Delete", "audit": discord.AuditLogAction.webhook_delete, "threshold": 2, "seconds": 30},
    "bot_add": {"label": "Bot Additions", "audit": discord.AuditLogAction.bot_add, "threshold": 1, "seconds": 60},
    "emoji_delete": {"label": "Emoji Delete", "audit": discord.AuditLogAction.emoji_delete, "threshold": 3, "seconds": 30},
    "emoji_create": {"label": "Emoji Create Spam", "audit": discord.AuditLogAction.emoji_create, "threshold": 5, "seconds": 30},
    "sticker_delete": {"label": "Sticker Delete", "audit": discord.AuditLogAction.sticker_delete, "threshold": 3, "seconds": 30},
    "guild_update": {"label": "Server Updates", "audit": discord.AuditLogAction.guild_update, "threshold": 2, "seconds": 30},
    "ban_spam": {"label": "Mass Bans", "audit": discord.AuditLogAction.ban, "threshold": 3, "seconds": 30},
    "kick_spam": {"label": "Mass Kicks", "audit": discord.AuditLogAction.kick, "threshold": 3, "seconds": 30},
    "member_prune": {"label": "Member Prune", "audit": discord.AuditLogAction.member_prune, "threshold": 1, "seconds": 60},
}


def default_rule(event: str) -> dict[str, Any]:
    base = PROTECTIONS[event]
    return {
        "enabled": True,
        "threshold": base["threshold"],
        "seconds": base["seconds"],
        "punishment": "strip_roles",
    }


class RuleModal(discord.ui.Modal):
    def __init__(self, cog: "AntiNuke", guild_id: int, event: str, current: dict[str, Any]) -> None:
        super().__init__(title=f"Edit {PROTECTIONS[event]['label']}")
        self.cog = cog
        self.guild_id = guild_id
        self.event = event
        self.threshold = discord.ui.TextInput(label="Trigger count", default=str(current.get("threshold", 3)), max_length=3)
        self.seconds = discord.ui.TextInput(label="Time window seconds", default=str(current.get("seconds", 30)), max_length=4)
        self.timeout_minutes = discord.ui.TextInput(label="Timeout minutes if punishment is timeout", default=str(current.get("timeout_minutes", 60)), max_length=5, required=False)
        self.add_item(self.threshold)
        self.add_item(self.seconds)
        self.add_item(self.timeout_minutes)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            threshold = max(1, min(50, int(str(self.threshold))))
            seconds = max(5, min(3600, int(str(self.seconds))))
            timeout_minutes = max(1, min(40320, int(str(self.timeout_minutes or 60))))
        except ValueError:
            await interaction.response.send_message("Use numbers only.", ephemeral=True)
            return
        settings = await self.cog.get_config(self.guild_id)
        rule = settings["rules"].setdefault(self.event, default_rule(self.event))
        rule["threshold"] = threshold
        rule["seconds"] = seconds
        rule["timeout_minutes"] = timeout_minutes
        await self.cog.save_config(self.guild_id, settings)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, settings, self.event), view=AntiNukePanel(self.cog, self.guild_id, self.event))


class ProtectionSelect(discord.ui.Select):
    def __init__(self, cog: "AntiNuke", guild_id: int, selected: str) -> None:
        self.cog = cog
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label=meta["label"], value=event, default=event == selected)
            for event, meta in PROTECTIONS.items()
        ]
        super().__init__(placeholder="Choose protection to edit", options=options[:25])

    async def callback(self, interaction: discord.Interaction) -> None:
        config = await self.cog.get_config(self.guild_id)
        selected = self.values[0]
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config, selected), view=AntiNukePanel(self.cog, self.guild_id, selected))


class PunishmentSelect(discord.ui.Select):
    def __init__(self, cog: "AntiNuke", guild_id: int, event: str, current: str) -> None:
        self.cog = cog
        self.guild_id = guild_id
        self.event = event
        options = [
            discord.SelectOption(label=label, value=value, default=value == current)
            for value, label in PUNISHMENTS.items()
        ]
        super().__init__(placeholder="Choose punishment", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        config = await self.cog.get_config(self.guild_id)
        rule = config["rules"].setdefault(self.event, default_rule(self.event))
        rule["punishment"] = self.values[0]
        await self.cog.save_config(self.guild_id, config)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config, self.event), view=AntiNukePanel(self.cog, self.guild_id, self.event))


class WhitelistModal(discord.ui.Modal, title="Whitelist User or Role"):
    target_id = discord.ui.TextInput(label="User ID or Role ID", placeholder="Paste the ID here", max_length=24)

    def __init__(self, cog: "AntiNuke", guild_id: int) -> None:
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not str(self.target_id).isdigit():
            await interaction.response.send_message("That ID does not look valid.", ephemeral=True)
            return
        config = await self.cog.get_config(self.guild_id)
        value = int(str(self.target_id))
        if value not in config["whitelist"]:
            config["whitelist"].append(value)
        await self.cog.save_config(self.guild_id, config)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config), view=AntiNukePanel(self.cog, self.guild_id))


class AntiNukePanel(discord.ui.View):
    def __init__(self, cog: "AntiNuke", guild_id: int, selected: str = "channel_delete") -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.selected = selected
        self.add_item(ProtectionSelect(cog, guild_id, selected))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        allowed = interaction.user.guild_permissions.administrator or await interaction.client.is_owner(interaction.user)
        if not allowed:
            await interaction.response.send_message("Only admins can use this panel.", ephemeral=True)
        return allowed

    @discord.ui.button(label="Toggle Bot", style=discord.ButtonStyle.primary)
    async def toggle_bot(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.cog.get_config(self.guild_id)
        config["enabled"] = not config.get("enabled", True)
        await self.cog.save_config(self.guild_id, config)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config, self.selected), view=AntiNukePanel(self.cog, self.guild_id, self.selected))

    @discord.ui.button(label="Toggle Rule", style=discord.ButtonStyle.secondary)
    async def toggle_rule(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.cog.get_config(self.guild_id)
        rule = config["rules"].setdefault(self.selected, default_rule(self.selected))
        rule["enabled"] = not rule.get("enabled", True)
        await self.cog.save_config(self.guild_id, config)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config, self.selected), view=AntiNukePanel(self.cog, self.guild_id, self.selected))

    @discord.ui.button(label="Edit Limits", style=discord.ButtonStyle.secondary)
    async def edit_limits(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.cog.get_config(self.guild_id)
        rule = config["rules"].setdefault(self.selected, default_rule(self.selected))
        await interaction.response.send_modal(RuleModal(self.cog, self.guild_id, self.selected, rule))

    @discord.ui.button(label="Punishment", style=discord.ButtonStyle.secondary)
    async def punishment(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.cog.get_config(self.guild_id)
        rule = config["rules"].setdefault(self.selected, default_rule(self.selected))
        view = discord.ui.View(timeout=120)
        view.add_item(PunishmentSelect(self.cog, self.guild_id, self.selected, rule.get("punishment", "strip_roles")))
        await interaction.response.send_message("Choose the punishment for this protection.", view=view, ephemeral=True)

    @discord.ui.button(label="Whitelist", style=discord.ButtonStyle.success)
    async def whitelist(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(WhitelistModal(self.cog, self.guild_id))

    @discord.ui.button(label="Auto Setup", style=discord.ButtonStyle.success)
    async def auto_setup(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = self.cog.default_config()
        await self.cog.save_config(self.guild_id, config)
        await interaction.response.edit_message(embed=self.cog.panel_embed(interaction.guild, config, self.selected), view=AntiNukePanel(self.cog, self.guild_id, self.selected))


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.events: dict[tuple[int, int, str], deque[float]] = defaultdict(lambda: deque(maxlen=50))

    antinuke = app_commands.Group(name="antinuke", description="Protect the server from destructive actions")

    def default_config(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "dm_owner": True,
            "rules": {event: default_rule(event) for event in PROTECTIONS},
            "whitelist": [],
            "recent_actions": [],
        }

    async def get_config(self, guild_id: int) -> dict[str, Any]:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        old_rules = settings.get("antinuke", {})
        config = settings.get("antinuke_v2") or self.default_config()
        config["enabled"] = settings.get("antinuke_enabled", config.get("enabled", True))
        config.setdefault("rules", {})
        config.setdefault("whitelist", settings.get("antinuke_whitelist", []))
        config.setdefault("recent_actions", [])
        for event in PROTECTIONS:
            merged = default_rule(event)
            merged.update(old_rules.get(event, {}))
            merged.update(config["rules"].get(event, {}))
            config["rules"][event] = merged
        return config

    async def save_config(self, guild_id: int, config: dict[str, Any]) -> None:
        await self.bot.db.set_settings_value(guild_id, "antinuke_v2", config, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild_id, "antinuke_enabled", config.get("enabled", True), self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild_id, "antinuke_whitelist", config.get("whitelist", []), self.bot.settings.default_prefix)

    def panel_embed(self, guild: discord.Guild, config: dict[str, Any], selected: str = "channel_delete") -> discord.Embed:
        rule = config["rules"].get(selected, default_rule(selected))
        active = sum(1 for item in config["rules"].values() if item.get("enabled", True))
        e = embed("Anti-Nuke Control Panel", "Use the menu and buttons below to customize protection.")
        e.add_field(name="System", value="Enabled" if config.get("enabled", True) else "Disabled", inline=True)
        e.add_field(name="Active Protections", value=f"{active}/{len(PROTECTIONS)}", inline=True)
        e.add_field(name="Whitelisted IDs", value=str(len(config.get("whitelist", []))), inline=True)
        e.add_field(
            name=f"Editing: {PROTECTIONS[selected]['label']}",
            value=(
                f"Enabled: `{rule.get('enabled', True)}`\n"
                f"Trigger: `{rule.get('threshold', 3)}` actions in `{rule.get('seconds', 30)}` seconds\n"
                f"Punishment: `{PUNISHMENTS.get(rule.get('punishment', 'strip_roles'), rule.get('punishment'))}`\n"
                f"Timeout: `{rule.get('timeout_minutes', 60)}` minutes"
            ),
            inline=False,
        )
        recent = config.get("recent_actions", [])[-5:]
        e.add_field(
            name="Recent Triggers",
            value="\n".join(f"`{item['event']}` by <@{item['actor_id']}>: `{item['punishment']}`" for item in recent) or "No triggers yet.",
            inline=False,
        )
        e.set_footer(text=f"Server: {guild.name}")
        return e

    @antinuke.command(name="panel", description="Open the clickable anti-nuke control panel")
    @app_admin()
    async def panel(self, interaction: discord.Interaction) -> None:
        config = await self.get_config(interaction.guild_id)
        await interaction.response.send_message(embed=self.panel_embed(interaction.guild, config), view=AntiNukePanel(self, interaction.guild_id), ephemeral=True)

    @antinuke.command(name="configure", description="Configure anti-nuke protection")
    @app_admin()
    async def configure(
        self,
        interaction: discord.Interaction,
        event: str,
        enabled: bool,
        threshold: app_commands.Range[int, 1, 50] = 3,
        seconds: app_commands.Range[int, 5, 3600] = 30,
        punishment: str = "strip_roles",
    ) -> None:
        if event not in PROTECTIONS:
            await interaction.response.send_message(f"Unknown event. Use one of: {', '.join(PROTECTIONS)}", ephemeral=True)
            return
        if punishment not in PUNISHMENTS:
            await interaction.response.send_message(f"Unknown punishment. Use one of: {', '.join(PUNISHMENTS)}", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        config["rules"][event] = {"enabled": enabled, "threshold": threshold, "seconds": seconds, "punishment": punishment, "timeout_minutes": 60}
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message(f"Anti-nuke `{event}` updated.", ephemeral=True)

    @antinuke.command(name="enable", description="Enable anti-nuke protection")
    @app_admin()
    async def enable(self, interaction: discord.Interaction) -> None:
        config = await self.get_config(interaction.guild_id)
        config["enabled"] = True
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message("Anti-nuke enabled.", ephemeral=True)

    @antinuke.command(name="disable", description="Disable anti-nuke protection")
    @app_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        config = await self.get_config(interaction.guild_id)
        config["enabled"] = False
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message("Anti-nuke disabled.", ephemeral=True)

    @antinuke.command(name="status", description="Show anti-nuke status")
    @app_admin()
    async def status(self, interaction: discord.Interaction) -> None:
        config = await self.get_config(interaction.guild_id)
        await interaction.response.send_message(embed=self.panel_embed(interaction.guild, config), ephemeral=True)

    @antinuke.command(name="whitelist", description="Whitelist a user or role from anti-nuke")
    @app_admin()
    async def whitelist(self, interaction: discord.Interaction, target_id: str) -> None:
        if not target_id.isdigit():
            await interaction.response.send_message("Paste a user ID or role ID.", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        value = int(target_id)
        if value not in config["whitelist"]:
            config["whitelist"].append(value)
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message("Whitelist updated.", ephemeral=True)

    @antinuke.command(name="unwhitelist", description="Remove a user or role from the whitelist")
    @app_admin()
    async def unwhitelist(self, interaction: discord.Interaction, target_id: str) -> None:
        if not target_id.isdigit():
            await interaction.response.send_message("Paste a user ID or role ID.", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        config["whitelist"] = [item for item in config["whitelist"] if item != int(target_id)]
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message("Whitelist updated.", ephemeral=True)

    async def actor_from_audit(self, guild: discord.Guild, action: discord.AuditLogAction) -> discord.Member | None:
        async for entry in guild.audit_logs(limit=3, action=action):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                continue
            if entry.user:
                return guild.get_member(entry.user.id)
        return None

    async def actor_from_ban_audit(self, guild: discord.Guild, user: discord.User) -> discord.Member | None:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if (discord.utils.utcnow() - entry.created_at).total_seconds() > 15:
                continue
            if entry.target and entry.target.id == user.id and entry.user:
                return guild.get_member(entry.user.id)
        return None

    async def protect_owner_from_ban(self, guild: discord.Guild, user: discord.User) -> bool:
        owner_ids = getattr(self.bot.settings, "owner_ids", set())
        if user.id not in owner_ids:
            return False

        actor = await self.actor_from_ban_audit(guild, user)
        try:
            await guild.unban(user, reason="Owner ID ban protection")
            unbanned = True
        except discord.HTTPException:
            unbanned = False

        punishment = "none"
        if actor and actor.id != guild.owner_id and actor.id != self.bot.user.id and not await configured_owner(self.bot, actor):
            me = guild.me
            if me and actor.top_role < me.top_role:
                roles = [role for role in actor.roles if not role.managed and role != guild.default_role and role < me.top_role]
                if roles:
                    try:
                        await actor.remove_roles(*roles, reason=f"Owner ID ban protection: banned {user}")
                        punishment = "strip_roles"
                    except discord.HTTPException:
                        punishment = "strip_roles_failed"

        await self.bot.db.execute(
            "INSERT INTO audit_events(guild_id,actor_id,target_id,event,data) VALUES(?,?,?,?,?)",
            guild.id,
            actor.id if actor else None,
            user.id,
            "owner_ban_protection",
            json.dumps({"unbanned": unbanned, "punishment": punishment}),
        )
        return True

    async def record(self, guild: discord.Guild, event: str) -> None:
        config = await self.get_config(guild.id)
        if not config.get("enabled", True):
            return
        action = PROTECTIONS[event]["audit"]
        actor = await self.actor_from_audit(guild, action)
        if actor is None or actor.id == guild.owner_id or actor.id == self.bot.user.id:
            return
        if actor.id in config["whitelist"] or any(role.id in config["whitelist"] for role in actor.roles):
            return
        rule = config["rules"].get(event, default_rule(event))
        if not rule.get("enabled", True):
            return
        now = time.monotonic()
        key = (guild.id, actor.id, event)
        self.events[key].append(now)
        threshold = int(rule.get("threshold", 3))
        seconds = int(rule.get("seconds", 30))
        hits = [stamp for stamp in self.events[key] if now - stamp <= seconds]
        if len(hits) >= threshold:
            await self.punish(actor, rule, event, config)

    async def punish(self, member: discord.Member, rule: dict[str, Any], event: str, config: dict[str, Any]) -> None:
        punishment = rule.get("punishment", "strip_roles")
        reason = f"Anti-nuke triggered: {event}"
        if punishment in {"ignore", "log_only"}:
            pass
        else:
            try:
                if punishment == "ban":
                    await member.ban(reason=reason)
                elif punishment == "kick":
                    await member.kick(reason=reason)
                elif punishment == "timeout":
                    minutes = int(rule.get("timeout_minutes", 60))
                    await member.timeout(discord.utils.utcnow() + dt.timedelta(minutes=minutes), reason=reason)
                elif punishment == "strip_roles":
                    roles = [r for r in member.roles if not r.managed and r != member.guild.default_role and r < member.guild.me.top_role]
                    if roles:
                        await member.remove_roles(*roles, reason=reason)
            except discord.HTTPException:
                punishment = f"{punishment}_failed"
        config["recent_actions"] = (config.get("recent_actions", []) + [{
            "event": event,
            "actor_id": member.id,
            "punishment": punishment,
            "at": int(time.time()),
        }])[-20:]
        await self.save_config(member.guild.id, config)
        await self.bot.db.execute(
            "INSERT INTO audit_events(guild_id,actor_id,event,data) VALUES(?,?,?,?)",
            member.guild.id,
            member.id,
            "antinuke",
            json.dumps({"event": event, "punishment": punishment}),
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self.record(channel.guild, "channel_delete")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self.record(channel.guild, "channel_create")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        await self.record(after.guild, "channel_update")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self.record(role.guild, "role_delete")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self.record(role.guild, "role_create")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if before.permissions != after.permissions or before.position != after.position:
            await self.record(after.guild, "role_update")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        await self.record(channel.guild, "webhook_create")
        await self.record(channel.guild, "webhook_delete")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            await self.record(member.guild, "bot_add")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if await self.protect_owner_from_ban(guild, user):
            return
        await self.record(guild, "ban_spam")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.record(member.guild, "kick_spam")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before: list[discord.Emoji], after: list[discord.Emoji]) -> None:
        if len(after) < len(before):
            await self.record(guild, "emoji_delete")
        elif len(after) > len(before):
            await self.record(guild, "emoji_create")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before: list[discord.GuildSticker], after: list[discord.GuildSticker]) -> None:
        if len(after) < len(before):
            await self.record(guild, "sticker_delete")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        await self.record(after, "guild_update")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AntiNuke(bot))
