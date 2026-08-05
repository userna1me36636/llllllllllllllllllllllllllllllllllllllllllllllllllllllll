from __future__ import annotations

import logging
from collections.abc import Iterable

import discord
from discord import app_commands
from discord.errors import NotFound
from discord.ext import commands

from bot.core.config import Settings
from bot.core.database import Database
from bot.core.logging import setup_logging


COGS: tuple[str, ...] = (
    "bot.cogs.help",
    "bot.cogs.admin",
    "bot.cogs.doctor",
    "bot.cogs.setup_tools",
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
        self.add_check(self._command_prefix_allowed)

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

    async def setup_hook(self) -> None:
        await self.db.init()
        for cog in COGS:
            if cog.endswith(".music") and not self.settings.enable_music:
                continue
            await self.load_extension(cog)
        if self.settings.auto_sync_commands:
            self.loop.create_task(self._sync_commands())

    async def _sync_commands(self) -> None:
        await self.wait_until_ready()
        synced = await self.tree.sync()
        self.log.info("Synced %s slash commands", len(synced))

    async def on_ready(self) -> None:
        self.log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")

    async def themed_embed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        if guild_id is not None:
            try:
                settings = await self.db.get_settings(guild_id, self.settings.default_prefix)
                theme = settings.get("theme", {})
                color = discord.Color(int(theme.get("color", color.value)))
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
        self.log.exception("Command error in %s", ctx.command, exc_info=error)
        await self.safe_context_reply(ctx, "Command Error")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, app_commands.MissingPermissions):
            embed = await self.themed_embed(interaction.guild_id, "Missing Permission")
        else:
            self.log.exception("Slash command error in %s", getattr(interaction.command, "qualified_name", "unknown"), exc_info=error)
            embed = await self.themed_embed(interaction.guild_id, "Command Error")
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
