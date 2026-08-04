from __future__ import annotations

import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_has_guild_permissions
from bot.core.utils import embed, level_for_xp, xp_for_level


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    level = app_commands.Group(name="levels", description="XP, ranks, and leaderboards")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        settings = await self.bot.db.get_settings(message.guild.id, self.bot.settings.default_prefix)
        if settings.get("levels_enabled", True) is False:
            return
        row = await self.bot.db.fetchrow("SELECT amount,last_message_at FROM xp WHERE guild_id=? AND user_id=?", message.guild.id, message.author.id)
        now = time.time()
        old_xp = row["amount"] if row else 0
        if row and now - row["last_message_at"] < 45:
            return
        gained = random.randint(12, 24)
        new_xp = old_xp + gained
        await self.bot.db.execute("INSERT INTO xp(guild_id,user_id,amount,last_message_at) VALUES(?,?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET amount=excluded.amount,last_message_at=excluded.last_message_at", message.guild.id, message.author.id, new_xp, now)
        if level_for_xp(new_xp) > level_for_xp(old_xp):
            await message.channel.send(embed=embed("Level Up", f"{message.author.mention} reached level {level_for_xp(new_xp)}."))

    @level.command(name="rank", description="Show rank")
    async def rank(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        row = await self.bot.db.fetchrow("SELECT amount FROM xp WHERE guild_id=? AND user_id=?", interaction.guild_id, member.id)
        xp = row["amount"] if row else 0
        lvl = level_for_xp(xp)
        e = embed("Rank", member.mention)
        e.add_field(name="Level", value=str(lvl))
        e.add_field(name="XP", value=f"{xp}/{xp_for_level(lvl + 1)}")
        await interaction.response.send_message(embed=e)

    @level.command(name="leaderboard", description="Show server XP leaders")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT user_id,amount FROM xp WHERE guild_id=? ORDER BY amount DESC LIMIT 10", interaction.guild_id)
        e = embed("Leaderboard")
        for i, row in enumerate(rows, start=1):
            e.add_field(name=f"#{i}", value=f"<@{row['user_id']}> - {row['amount']} XP", inline=False)
        await interaction.response.send_message(embed=e)

    @level.command(name="toggle", description="Turn levels on or off")
    @app_has_guild_permissions(manage_guild=True)
    async def toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "levels_enabled", enabled, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Levels enabled: `{enabled}`", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leveling(bot))
