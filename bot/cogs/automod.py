from __future__ import annotations

import datetime as dt
import re
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


INVITE_RE = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.I)
LINK_RE = re.compile(r"https?://|www\.", re.I)
BAD_WORDS = {"slur", "scamword"}


class Automod(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.recent: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=12))
        self.mentions: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=8))

    automod = app_commands.Group(name="automod", description="Configure automatic moderation")

    @automod.command(name="configure", description="Configure an automod rule")
    @app_admin()
    async def configure(self, interaction: discord.Interaction, rule: str, enabled: bool, punishment: str = "delete") -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("automod", {})
        data[rule.lower()] = {"enabled": enabled, "punishment": punishment.lower()}
        await self.bot.db.set_settings_value(interaction.guild_id, "automod", data, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Automod `{rule}` set to `{enabled}` with `{punishment}`.", ephemeral=True)

    @automod.command(name="status", description="Show automod configuration")
    @app_admin()
    async def status(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = embed("Automod Status")
        for rule, data in settings.get("automod", {}).items():
            e.add_field(name=rule, value=f"enabled={data.get('enabled')} punishment={data.get('punishment')}", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @automod.command(name="links", description="Block links")
    @app_admin()
    async def links(self, interaction: discord.Interaction, enabled: bool = True) -> None:
        await self._toggle(interaction, "links", enabled)

    @automod.command(name="invites", description="Block Discord invite links")
    @app_admin()
    async def invites(self, interaction: discord.Interaction, enabled: bool = True) -> None:
        await self._toggle(interaction, "invites", enabled)

    @automod.command(name="words", description="Set comma-separated banned words")
    @app_admin()
    async def words(self, interaction: discord.Interaction, words: str) -> None:
        banned = [word.strip().lower() for word in words.split(",") if word.strip()]
        await self.bot.db.set_settings_value(interaction.guild_id, "automod_words", banned, self.bot.settings.default_prefix)
        await self._toggle(interaction, "profanity", True, respond=False)
        await interaction.response.send_message(f"Saved {len(banned)} banned word(s).", ephemeral=True)

    async def _toggle(self, interaction: discord.Interaction, rule: str, enabled: bool, respond: bool = True) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("automod", {})
        data[rule] = {"enabled": enabled, "punishment": data.get(rule, {}).get("punishment", "delete")}
        await self.bot.db.set_settings_value(interaction.guild_id, "automod", data, self.bot.settings.default_prefix)
        if respond:
            await interaction.response.send_message(f"Automod `{rule}` set to `{enabled}`.", ephemeral=True)

    async def punish(self, message: discord.Message, reason: str, punishment: str) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        if punishment == "timeout" and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(discord.utils.utcnow() + dt.timedelta(minutes=10), reason=reason)
            except Exception:
                pass
        await self.bot.db.execute("INSERT INTO audit_events(guild_id,actor_id,target_id,event,data) VALUES(?,?,?,?,?)", message.guild.id, self.bot.user.id, message.author.id, "automod", f'{{"reason":"{reason}"}}')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.author, discord.Member):
            return
        if message.author.guild_permissions.manage_messages:
            return
        settings = await self.bot.db.get_settings(message.guild.id, self.bot.settings.default_prefix)
        rules = settings.get("automod", {})
        banned_words = set(settings.get("automod_words", [])) or BAD_WORDS
        content = message.content or ""
        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        self.recent[key].append(now)
        self.mentions[key].append(now) if len(message.mentions) >= 4 else None
        checks = {
            "links": bool(LINK_RE.search(content)),
            "invites": bool(INVITE_RE.search(content)),
            "caps": len(content) > 12 and sum(ch.isupper() for ch in content) / max(1, len(content)) > 0.75,
            "profanity": any(word in content.lower() for word in banned_words),
            "spam": len(self.recent[key]) >= 6 and now - self.recent[key][0] <= 7,
            "mention_spam": len(message.mentions) >= 6,
        }
        for rule, hit in checks.items():
            cfg = rules.get(rule, {})
            if hit and cfg.get("enabled"):
                await self.punish(message, rule, cfg.get("punishment", "delete"))
                break


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Automod(bot))
