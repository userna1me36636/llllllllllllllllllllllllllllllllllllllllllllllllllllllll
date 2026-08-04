from __future__ import annotations

import datetime as dt
from pathlib import Path

import discord
from discord.ext import commands, tasks

from bot.core.config import DATA_DIR
from bot.core.utils import embed


class EventLogging(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.backups.start()
        self.temp_actions.start()

    def cog_unload(self) -> None:
        self.backups.cancel()
        self.temp_actions.cancel()

    async def log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        channel_id = settings.get("log_channel")
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def send_log(self, guild: discord.Guild, title: str, body: str) -> None:
        channel = await self.log_channel(guild)
        if channel:
            await channel.send(embed=embed(title, body))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            await self.send_log(message.guild, "Message Deleted", f"{message.author.mention} in {message.channel.mention}\n{message.clean_content[:1500]}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild and not before.author.bot and before.content != after.content:
            await self.send_log(before.guild, "Message Edited", f"{before.author.mention} in {before.channel.mention}\nBefore: {before.clean_content[:700]}\nAfter: {after.clean_content[:700]}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.send_log(member.guild, "Member Joined", f"{member.mention} ({member.id})")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.send_log(member.guild, "Member Left", f"{member} ({member.id})")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.send_log(guild, "Member Banned", f"{user} ({user.id})")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self.send_log(guild, "Member Unbanned", f"{user} ({user.id})")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel != after.channel:
            await self.send_log(member.guild, "Voice Update", f"{member.mention}: {before.channel} -> {after.channel}")

    @tasks.loop(minutes=30)
    async def temp_actions(self) -> None:
        rows = await self.bot.db.fetchall("SELECT * FROM temp_actions WHERE expires_at<=?", discord.utils.utcnow().timestamp())
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild and row["action"] == "unban":
                user = await self.bot.fetch_user(row["user_id"])
                try:
                    await guild.unban(user, reason="Temporary ban expired")
                except discord.HTTPException:
                    pass
            await self.bot.db.execute("DELETE FROM temp_actions WHERE id=?", row["id"])

    @tasks.loop(minutes=30)
    async def backups(self) -> None:
        interval = max(30, int(self.bot.settings.backup_interval_minutes))
        minute = dt.datetime.now().minute
        if minute % max(1, min(59, interval // 30)) != 0:
            return
        stamp = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        self.bot.db.backup_to(DATA_DIR / "backups" / f"bot-{stamp}.sqlite3")

    @temp_actions.before_loop
    @backups.before_loop
    async def before_tasks(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventLogging(bot))
