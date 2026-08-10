from __future__ import annotations

import logging
import secrets
from collections.abc import Iterable

import discord
from discord import app_commands
from discord.errors import NotFound
from discord.ext import commands

from bot.core.config import Settings
from bot.core.database import Database
from bot.core.logging import setup_logging
from bot.core.utils import theme_color_from_data
from bot.services.dashboard import start_dashboard


COGS: tuple[str, ...] = (
    "bot.cogs.help",
    "bot.cogs.admin",
    "bot.cogs.doctor",
    "bot.cogs.setup_tools",
    "bot.cogs.growth_safety",
    "bot.cogs.community_suite",
    "bot.cogs.engagement",
    "bot.cogs.reliability",
    "bot.cogs.management_suite",
    "bot.cogs.moderation",
    "bot.cogs.automod",
    "bot.cogs.antinuke",
    "bot.cogs.godmode",
    "bot.cogs.jointocreate",
    "bot.cogs.music",
    "bot.cogs.tickets",
    "bot.cogs.roles",
    "bot.cogs.welcome",
    "bot.cogs.leveling",
    "bot.cogs.giveaways",
    "bot.cogs.economy",
    "bot.cogs.utility",
    "bot.cogs.event_logging",
    "bot.cogs.command_menu",
    "bot.cogs.ai_chat",
    "bot.cogs.vouch",
    "bot.cogs.server_backup",
)


async def dynamic_prefix(bot: "AllInOneBot", message: discord.Message) -> Iterable[str]:
    if message.guild is None:
        return commands.when_mentioned_or(bot.settings.default_prefix)(bot, message)
    settings = await bot.db.get_settings(message.guild.id, bot.settings.default_prefix)
    prefixes = list(settings.get("prefixes") or [settings.get("prefix", bot.settings.default_prefix)])
    if bot.settings.default_prefix not in prefixes:
        prefixes.insert(0, bot.settings.default_prefix)
    overrides = settings.get("command_prefix_overrides", {})
    for command_prefixes in overrides.values():
        for prefix in command_prefixes:
            if prefix not in prefixes:
                prefixes.append(prefix)
    return commands.when_mentioned_or(*prefixes)(bot, message)


class AllInOneBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.moderation = True
        intents.guilds = True
        intents.voice_states = True
        super().__init__(
            command_prefix=dynamic_prefix,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
            case_insensitive=True,
        )
        self.settings = settings
        if settings.owner_ids:
            self.owner_ids = set(settings.owner_ids)
        self.db = Database(settings.database_url)
        self.started_at = discord.utils.utcnow()
        self.log = logging.getLogger("bot")
        self._prefix_cooldowns: dict[tuple[int, int, str], float] = {}
        self.failed_cogs: dict[str, str] = {}
        self.add_check(self._command_prefix_allowed)
        self.add_check(self._feature_command_allowed)

    async def _command_prefix_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or ctx.command is None:
            return True
        settings = await self.db.get_settings(ctx.guild.id, self.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        allowed = overrides.get(ctx.command.qualified_name) or overrides.get(ctx.command.name)
        if not allowed:
            return True
        if ctx.prefix == self.settings.default_prefix:
            return True
        return ctx.prefix in allowed

    async def _feature_command_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or ctx.command is None:
            return True
        settings = await self.db.get_settings(ctx.guild.id, self.settings.default_prefix)
        root = ctx.command.qualified_name.split()[0]
        feature_flags = settings.get("feature_flags", {})
        if feature_flags.get(root) is False:
            await self.safe_context_reply(ctx, "Feature Disabled")
            return False
        role_rules = settings.get("command_role_permissions", {})
        allowed_roles = role_rules.get(ctx.command.qualified_name) or role_rules.get(root)
        if allowed_roles and isinstance(ctx.author, discord.Member):
            if not any(role.id in allowed_roles for role in ctx.author.roles) and not ctx.author.guild_permissions.administrator:
                await self.safe_context_reply(ctx, "Command Locked")
                return False
        cooldowns = settings.get("command_cooldowns", {})
        seconds = int(cooldowns.get(ctx.command.qualified_name, cooldowns.get(root, 0)) or 0)
        if seconds > 0:
            key = (ctx.guild.id, ctx.author.id, ctx.command.qualified_name)
            now = discord.utils.utcnow().timestamp()
            ready_at = self._prefix_cooldowns.get(key, 0)
            if now < ready_at:
                await self.safe_context_reply(ctx, "Cooldown Active", f"Try again in `{int(ready_at - now)}` seconds.")
                return False
            self._prefix_cooldowns[key] = now + seconds
        return True

    async def setup_hook(self) -> None:
        await self.db.init()
        for cog in COGS:
            if cog.endswith(".music") and not self.settings.enable_music:
                continue
            try:
                await self.load_extension(cog)
            except Exception as exc:
                self.failed_cogs[cog] = f"{type(exc).__name__}: {str(exc)[:300]}"
                self.log.exception("Could not load extension %s", cog)
        if self.settings.auto_sync_commands:
            self.loop.create_task(self._sync_commands())
        if self.settings.dashboard_enabled:
            self.loop.create_task(start_dashboard(self))

    async def _sync_commands(self) -> None:
        await self.wait_until_ready()
        synced = await self.tree.sync()
        self.log.info("Synced %s slash commands", len(synced))

    async def on_ready(self) -> None:
        self.log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def on_command_completion(self, ctx: commands.Context) -> None:
        if ctx.guild is None or ctx.command is None:
            return
        await self.log_command_usage(ctx.guild.id, ctx.author.id, ctx.channel.id, ctx.command.qualified_name, "ok")

    async def log_command_usage(self, guild_id: int, user_id: int, channel_id: int, command: str, status: str) -> None:
        try:
            await self.db.execute(
                "INSERT INTO audit_events(guild_id,actor_id,target_id,event,data) VALUES(?,?,?,?,?)",
                guild_id,
                user_id,
                channel_id,
                "command_usage",
                __import__("json").dumps({"command": command, "status": status}),
            )
            settings = await self.db.get_settings(guild_id, self.settings.default_prefix)
            log_channel_id = settings.get("command_log_channel")
            guild = self.get_guild(guild_id)
            channel = guild.get_channel(int(log_channel_id)) if guild and log_channel_id else None
            if isinstance(channel, discord.TextChannel):
                await channel.send(embed=await self.themed_embed(guild_id, "Command Used", f"<@{user_id}> used `{command}` in <#{channel_id}>.\nStatus: `{status}`"))
        except Exception:
            self.log.debug("Could not record command usage", exc_info=True)

    async def themed_embed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        if guild_id is not None:
            try:
                settings = await self.db.get_settings(guild_id, self.settings.default_prefix)
                theme = settings.get("theme", {})
                color = theme_color_from_data(theme, color)
            except Exception:
                pass
        return discord.Embed(title=title, description=description, color=color)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
            return
        if isinstance(error, commands.MissingPermissions):
            await self.safe_context_reply(ctx, "Missing Permission")
            return
        if isinstance(error, commands.BadArgument):
            await self.safe_context_reply(ctx, "Bad Input", str(error))
            return
        error_id = secrets.token_hex(3).upper()
        self.log.exception("Command error %s in %s", error_id, ctx.command, exc_info=error)
        if ctx.guild is not None and ctx.command is not None:
            await self.log_command_usage(ctx.guild.id, ctx.author.id, ctx.channel.id, ctx.command.qualified_name, "error")
        await self.safe_context_reply(ctx, "Command Error", f"Error ID: `{error_id}`")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, app_commands.MissingPermissions):
            embed = await self.themed_embed(interaction.guild_id, "Missing Permission")
        else:
            error_id = secrets.token_hex(3).upper()
            self.log.exception("Slash command error %s in %s", error_id, getattr(interaction.command, "qualified_name", "unknown"), exc_info=error)
            embed = await self.themed_embed(interaction.guild_id, "Command Error", f"Error ID: `{error_id}`")
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except NotFound:
            self.log.warning("Could not reply because the interaction expired.")

    async def safe_context_reply(self, ctx: commands.Context, title: str, description: str | None = None) -> None:
        message = await self.themed_embed(ctx.guild.id if ctx.guild else None, title, description)
        try:
            if ctx.interaction and ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(embed=message, ephemeral=True)
            else:
                await ctx.reply(embed=message, mention_author=False)
        except NotFound:
            self.log.warning("Could not reply because the interaction expired.")


def create_bot(settings: Settings) -> AllInOneBot:
    setup_logging(settings.log_level)
    return AllInOneBot(settings)
