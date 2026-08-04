from __future__ import annotations

import logging
from collections.abc import Iterable

import discord
from discord.errors import NotFound
from discord.ext import commands

from bot.core.config import Settings
from bot.core.database import Database
from bot.core.logging import setup_logging


COGS: tuple[str, ...] = (
    "bot.cogs.help",
    "bot.cogs.admin",
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
    "bot.cogs.server_backup",
    "bot.cogs.companion_bots",
)


async def dynamic_prefix(bot: "AllInOneBot", message: discord.Message) -> Iterable[str]:
    if message.guild is None:
        return commands.when_mentioned_or(bot.settings.default_prefix)(bot, message)
    settings = await bot.db.get_settings(message.guild.id, bot.settings.default_prefix)
    prefixes = list(settings.get("prefixes") or [settings.get("prefix", bot.settings.default_prefix)])
    overrides = settings.get("command_prefix_overrides", {})
    for command_prefixes in overrides.values():
        for prefix in command_prefixes:
            if prefix not in prefixes:
                prefixes.append(prefix)
    for special_prefix in ("-", "."):
        if special_prefix not in prefixes:
            prefixes.append(special_prefix)
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
        root_name = ctx.command.root_parent.name if ctx.command.root_parent else ctx.command.name
        if allowed:
            return ctx.prefix in allowed
        if ctx.prefix == "-" and root_name != "vc":
            return False
        if ctx.prefix == "." and root_name != "ggive":
            return False
        return True

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

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        error = getattr(error, "original", error)
        if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
            return
        if isinstance(error, commands.MissingPermissions):
            await self.safe_context_reply(ctx, "You do not have permission to use that command.")
            return
        if isinstance(error, commands.BadArgument):
            await self.safe_context_reply(ctx, f"Bad input: {error}")
            return
        self.log.exception("Command error in %s", ctx.command, exc_info=error)
        await self.safe_context_reply(ctx, "Something went wrong while running that command.")

    async def safe_context_reply(self, ctx: commands.Context, content: str) -> None:
        try:
            if ctx.interaction and ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(content, ephemeral=True)
            else:
                await ctx.reply(content, mention_author=False)
        except NotFound:
            self.log.warning("Could not reply because the interaction expired.")


def create_bot(settings: Settings) -> AllInOneBot:
    setup_logging(settings.log_level)
    return AllInOneBot(settings)
