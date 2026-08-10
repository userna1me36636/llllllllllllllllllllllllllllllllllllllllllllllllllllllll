from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin


class Reliability(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_health: dict[int, str] = {}
        self._last_backup_at = 0.0
        self.background_checks.start()

    def cog_unload(self) -> None:
        self.background_checks.cancel()

    health = app_commands.Group(name="health", description="Service health and owner alerts")
    databackup = app_commands.Group(name="databackup", description="Automatic bot database backups")
    testmode = app_commands.Group(name="testmode", description="Safely preview bot systems")

    async def health_report(self, guild: discord.Guild) -> tuple[str, list[str]]:
        issues: list[str] = []
        try:
            await self.bot.db.fetchrow("SELECT 1")
        except Exception as exc:
            issues.append(f"Database: {type(exc).__name__}")
        failed = getattr(self.bot, "failed_cogs", {})
        if failed:
            issues.append(f"Failed modules: {len(failed)}")
        me = guild.me
        if me is None:
            issues.append("Discord member cache unavailable")
        else:
            needed = {
                "manage_channels": "Manage Channels",
                "manage_roles": "Manage Roles",
                "moderate_members": "Moderate Members",
                "kick_members": "Kick Members",
                "ban_members": "Ban Members",
                "view_audit_log": "View Audit Log",
            }
            missing = [label for key, label in needed.items() if not getattr(me.guild_permissions, key, False)]
            if missing:
                issues.append("Permissions: " + ", ".join(missing))
        oauth_keys = ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_OAUTH_REDIRECT_URI", "OAUTH_STATE_SECRET")
        if not all(os.getenv(key, "").strip() for key in oauth_keys):
            issues.append("Discord OAuth is incomplete")
        stripe_values = (os.getenv("STRIPE_SECRET_KEY", "").strip(), os.getenv("STRIPE_WEBHOOK_SECRET", "").strip())
        if any(stripe_values) and not all(stripe_values):
            issues.append("Stripe configuration is incomplete")
        return ("Healthy" if not issues else "Needs attention"), issues

    @health.command(name="status", description="Check database, modules, OAuth, Stripe and permissions")
    async def health_status(self, interaction: discord.Interaction) -> None:
        status, issues = await self.health_report(interaction.guild)
        text = "All checked systems are ready." if not issues else "\n".join(f"`FIX` {issue}" for issue in issues)
        await interaction.response.send_message(embed=await self.bot.themed_embed(interaction.guild_id, status, text), ephemeral=True)

    @health.command(name="alerts", description="Choose where owner health alerts are sent")
    @app_admin()
    async def health_alerts(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "health_alert_channel", channel.id if channel else None, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Health alerts {'will go to ' + channel.mention if channel else 'are disabled'}.", ephemeral=True)

    async def create_database_backup(self) -> Path:
        folder = Path(__file__).resolve().parents[2] / "data" / "automatic_backups"
        destination = folder / f"ainbot-{int(time.time())}.sqlite3"
        await asyncio.to_thread(self.bot.db.backup_to, destination)
        backups = sorted(folder.glob("ainbot-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
        for old in backups[14:]:
            old.unlink(missing_ok=True)
        self._last_backup_at = time.time()
        return destination

    @databackup.command(name="now", description="Create a database backup immediately")
    @app_admin()
    async def databackup_now(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        path = await self.create_database_backup()
        await interaction.followup.send(f"Database backup created: `{path.name}`. Railway persistent storage is still recommended.", ephemeral=True)

    @databackup.command(name="status", description="Show automatic database backup status")
    @app_admin()
    async def databackup_status(self, interaction: discord.Interaction) -> None:
        folder = Path(__file__).resolve().parents[2] / "data" / "automatic_backups"
        backups = sorted(folder.glob("ainbot-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True) if folder.exists() else []
        latest = f"<t:{int(backups[0].stat().st_mtime)}:R>" if backups else "No backup yet"
        await interaction.response.send_message(embed=await self.bot.themed_embed(interaction.guild_id, "Database Backups", f"Stored backups: `{len(backups)}`\nLatest: {latest}\nSchedule: every six hours\nRetention: latest 14 files"), ephemeral=True)

    @testmode.command(name="welcome", description="Preview the configured welcome without pinging anyone")
    @app_admin()
    async def test_welcome(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        welcome = settings.get("welcome", {})
        message = str(welcome.get("message", "Welcome {mention} to {server}."))
        message = message.replace("{mention}", interaction.user.mention).replace("{server}", interaction.guild.name).replace("{user}", interaction.user.display_name)
        await interaction.response.send_message(embed=await self.bot.themed_embed(interaction.guild_id, "Welcome Test", message), ephemeral=True)

    @testmode.command(name="verification", description="Check verification configuration without assigning a role")
    @app_admin()
    async def test_verification(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        role = interaction.guild.get_role(int(settings.get("verify_role", 0) or 0))
        age = (discord.utils.utcnow() - interaction.user.created_at).days
        minimum = int(settings.get("verify_min_account_days", 0) or 0)
        text = f"Role: {role.mention if role else 'Missing'}\nYour account age: `{age}` days\nMinimum: `{minimum}` days\nResult: `{'PASS' if role and age >= minimum else 'FIX'}`"
        await interaction.response.send_message(embed=await self.bot.themed_embed(interaction.guild_id, "Verification Test", text), ephemeral=True)

    @testmode.command(name="purchase", description="Preview purchase fulfillment without charging or assigning a role")
    @app_admin()
    async def test_purchase(self, interaction: discord.Interaction, product: str = "all") -> None:
        role_names = {"vc_perms": "VC Perms", "anti_reject": "Anti-Reject", "godmode": "VC Godmode", "all": "All Access"}
        role_name = role_names.get(product, "Unknown product")
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        manageable = bool(role and interaction.guild.me and role < interaction.guild.me.top_role)
        text = f"Product: `{product}`\nExpected role: `{role_name}`\nExisting role: `{'YES' if role else 'WILL CREATE'}`\nManageable: `{'YES' if manageable or role is None else 'NO'}`\nNo payment or role change was made."
        await interaction.response.send_message(embed=await self.bot.themed_embed(interaction.guild_id, "Purchase Test", text), ephemeral=True)

    @tasks.loop(seconds=30)
    async def background_checks(self) -> None:
        now = time.time()
        rows = await self.bot.db.fetchall("SELECT id,user_id,guild_id,channel_id,message FROM reminders WHERE delivered=0 AND remind_at<=? ORDER BY id LIMIT 50", now)
        for row in rows:
            user = self.bot.get_user(int(row["user_id"]))
            if user is None:
                try:
                    user = await self.bot.fetch_user(int(row["user_id"]))
                except discord.HTTPException:
                    continue
            delivered = False
            try:
                await user.send(f"Reminder: {row['message']}")
                delivered = True
            except discord.Forbidden:
                guild = self.bot.get_guild(int(row["guild_id"] or 0))
                channel = guild.get_channel(int(row["channel_id"] or 0)) if guild else None
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(f"<@{row['user_id']}> reminder: {row['message']}", allowed_mentions=discord.AllowedMentions(users=True))
                        delivered = True
                    except discord.HTTPException:
                        pass
            if delivered:
                await self.bot.db.execute("UPDATE reminders SET delivered=1 WHERE id=?", row["id"])

        if now - self._last_backup_at >= 21600:
            try:
                await self.create_database_backup()
            except Exception:
                self.bot.log.exception("Automatic database backup failed")

        if int(now) % 300 < 30:
            for guild in self.bot.guilds:
                status, issues = await self.health_report(guild)
                signature = json.dumps(issues, sort_keys=True)
                old_signature = self._last_health.get(guild.id)
                self._last_health[guild.id] = signature
                if not issues or signature == old_signature:
                    continue
                settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
                channel = guild.get_channel(int(settings.get("health_alert_channel", 0) or 0))
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(embed=await self.bot.themed_embed(guild.id, "AinBot Health Alert", "\n".join(f"`FIX` {issue}" for issue in issues)))
                    except discord.HTTPException:
                        pass

    @background_checks.before_loop
    async def before_background_checks(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reliability(bot))
