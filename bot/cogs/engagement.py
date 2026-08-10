from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin


class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sticky_counts: dict[tuple[int, int], int] = {}
        self.process_timers.start()

    def cog_unload(self) -> None:
        self.process_timers.cancel()

    sticky = app_commands.Group(name="sticky", description="Keep an important message at the bottom of a channel")
    announcement = app_commands.Group(name="announcement", description="Send or schedule server announcements")
    temprole = app_commands.Group(name="temprole", description="Give roles that automatically expire")

    async def themed(self, guild_id: int, title: str, description: str | None = None) -> discord.Embed:
        return await self.bot.themed_embed(guild_id, title, description)

    @sticky.command(name="set", description="Keep a message visible at the bottom of a channel")
    @app_admin()
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None,
        refresh_after: app_commands.Range[int, 2, 50] = 5,
    ) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("Choose a text channel.", ephemeral=True)
            return
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        sticky_data = settings.get("sticky_messages", {})
        old = sticky_data.get(str(target.id), {})
        old_message_id = old.get("message_id")
        if old_message_id:
            try:
                old_message = await target.fetch_message(int(old_message_id))
                await old_message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        panel = await self.themed(interaction.guild_id, "Pinned Information", message[:4000])
        posted = await target.send(embed=panel)
        sticky_data[str(target.id)] = {
            "text": message[:4000],
            "refresh_after": int(refresh_after),
            "message_id": posted.id,
        }
        await self.bot.db.set_settings_value(interaction.guild_id, "sticky_messages", sticky_data, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Sticky message enabled in {target.mention}.", ephemeral=True)

    @sticky.command(name="off", description="Disable the sticky message in a channel")
    @app_admin()
    async def sticky_off(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("Choose a text channel.", ephemeral=True)
            return
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        sticky_data = settings.get("sticky_messages", {})
        old = sticky_data.pop(str(target.id), None)
        await self.bot.db.set_settings_value(interaction.guild_id, "sticky_messages", sticky_data, self.bot.settings.default_prefix)
        if old and old.get("message_id"):
            try:
                await (await target.fetch_message(int(old["message_id"]))).delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        await interaction.response.send_message(f"Sticky message disabled in {target.mention}.", ephemeral=True)

    @sticky.command(name="status", description="Show configured sticky-message channels")
    @app_admin()
    async def sticky_status(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        rows = []
        for channel_id, data in settings.get("sticky_messages", {}).items():
            rows.append(f"<#{channel_id}> — refresh after `{data.get('refresh_after', 5)}` messages")
        await interaction.response.send_message(
            embed=await self.themed(interaction.guild_id, "Sticky Messages", "\n".join(rows) or "No sticky messages configured."),
            ephemeral=True,
        )

    @announcement.command(name="schedule", description="Schedule an announcement for later")
    @app_admin()
    async def announcement_schedule(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        minutes_from_now: app_commands.Range[int, 1, 43200],
        title: str,
        message: str,
    ) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        scheduled = settings.get("scheduled_announcements", [])
        item_id = max((int(item.get("id", 0)) for item in scheduled), default=0) + 1
        send_at = discord.utils.utcnow() + timedelta(minutes=int(minutes_from_now))
        scheduled.append({
            "id": item_id,
            "channel_id": channel.id,
            "title": title[:256],
            "message": message[:4000],
            "send_at": send_at.isoformat(),
            "created_by": interaction.user.id,
        })
        await self.bot.db.set_settings_value(interaction.guild_id, "scheduled_announcements", scheduled[-100:], self.bot.settings.default_prefix)
        await interaction.response.send_message(
            f"Announcement `#{item_id}` will be sent in {channel.mention} {discord.utils.format_dt(send_at, style='R')}.",
            ephemeral=True,
        )

    @announcement.command(name="list", description="List scheduled announcements")
    @app_admin()
    async def announcement_list(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        rows = []
        for item in settings.get("scheduled_announcements", [])[:20]:
            try:
                when = discord.utils.parse_time(item["send_at"])
                time_text = discord.utils.format_dt(when, style="R") if when else "unknown time"
            except (KeyError, TypeError, ValueError):
                time_text = "unknown time"
            rows.append(f"`#{item.get('id')}` <#{item.get('channel_id')}> — **{item.get('title', 'Announcement')}** — {time_text}")
        await interaction.response.send_message(
            embed=await self.themed(interaction.guild_id, "Scheduled Announcements", "\n".join(rows) or "Nothing is scheduled."),
            ephemeral=True,
        )

    @announcement.command(name="cancel", description="Cancel a scheduled announcement")
    @app_admin()
    async def announcement_cancel(self, interaction: discord.Interaction, announcement_id: int) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        scheduled = settings.get("scheduled_announcements", [])
        remaining = [item for item in scheduled if int(item.get("id", 0)) != announcement_id]
        await self.bot.db.set_settings_value(interaction.guild_id, "scheduled_announcements", remaining, self.bot.settings.default_prefix)
        text = "Scheduled announcement cancelled." if len(remaining) != len(scheduled) else "That announcement ID was not found."
        await interaction.response.send_message(text, ephemeral=True)

    @temprole.command(name="give", description="Give a role that is removed automatically")
    @app_admin()
    async def temprole_give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        minutes: app_commands.Range[int, 1, 43200],
        reason: str = "Temporary access",
    ) -> None:
        if role >= interaction.guild.me.top_role or role.is_default() or role.managed:
            await interaction.response.send_message("I cannot manage that role. Move AinBot above it first.", ephemeral=True)
            return
        await member.add_roles(role, reason=f"{reason} — assigned by {interaction.user}")
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        entries = settings.get("temporary_roles", [])
        entries = [item for item in entries if not (int(item.get("member_id", 0)) == member.id and int(item.get("role_id", 0)) == role.id)]
        expires_at = discord.utils.utcnow() + timedelta(minutes=int(minutes))
        entries.append({"member_id": member.id, "role_id": role.id, "expires_at": expires_at.isoformat(), "reason": reason[:200]})
        await self.bot.db.set_settings_value(interaction.guild_id, "temporary_roles", entries[-500:], self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Gave {role.mention} to {member.mention} until {discord.utils.format_dt(expires_at, style='R')}.", ephemeral=True)

    @temprole.command(name="remove", description="Remove a temporary role early")
    @app_admin()
    async def temprole_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if role in member.roles and role < interaction.guild.me.top_role:
            await member.remove_roles(role, reason=f"Temporary role removed by {interaction.user}")
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        entries = settings.get("temporary_roles", [])
        entries = [item for item in entries if not (int(item.get("member_id", 0)) == member.id and int(item.get("role_id", 0)) == role.id)]
        await self.bot.db.set_settings_value(interaction.guild_id, "temporary_roles", entries, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Removed the temporary {role.mention} assignment for {member.mention}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return
        settings = await self.bot.db.get_settings(message.guild.id, self.bot.settings.default_prefix)
        sticky_data = settings.get("sticky_messages", {})
        data = sticky_data.get(str(message.channel.id))
        if not data:
            return
        key = (message.guild.id, message.channel.id)
        self._sticky_counts[key] = self._sticky_counts.get(key, 0) + 1
        if self._sticky_counts[key] < int(data.get("refresh_after", 5)):
            return
        self._sticky_counts[key] = 0
        old_message_id = data.get("message_id")
        if old_message_id:
            try:
                await (await message.channel.fetch_message(int(old_message_id))).delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        try:
            posted = await message.channel.send(embed=await self.themed(message.guild.id, "Pinned Information", str(data.get("text", ""))[:4000]))
        except (discord.Forbidden, discord.HTTPException):
            return
        data["message_id"] = posted.id
        sticky_data[str(message.channel.id)] = data
        await self.bot.db.set_settings_value(message.guild.id, "sticky_messages", sticky_data, self.bot.settings.default_prefix)

    @tasks.loop(seconds=30)
    async def process_timers(self) -> None:
        now = discord.utils.utcnow()
        for guild in list(self.bot.guilds):
            settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
            changed_announcements = False
            remaining_announcements = []
            for item in settings.get("scheduled_announcements", []):
                try:
                    send_at = discord.utils.parse_time(item["send_at"])
                except (KeyError, TypeError, ValueError):
                    send_at = None
                if send_at is None or send_at > now:
                    remaining_announcements.append(item)
                    continue
                channel = guild.get_channel(int(item.get("channel_id", 0)))
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(embed=await self.themed(guild.id, str(item.get("title", "Announcement"))[:256], str(item.get("message", ""))[:4000]))
                    except (discord.Forbidden, discord.HTTPException):
                        remaining_announcements.append(item)
                        continue
                changed_announcements = True
            if changed_announcements:
                await self.bot.db.set_settings_value(guild.id, "scheduled_announcements", remaining_announcements, self.bot.settings.default_prefix)

            changed_roles = False
            remaining_roles = []
            for item in settings.get("temporary_roles", []):
                try:
                    expires_at = discord.utils.parse_time(item["expires_at"])
                except (KeyError, TypeError, ValueError):
                    expires_at = None
                if expires_at is None or expires_at > now:
                    remaining_roles.append(item)
                    continue
                member = guild.get_member(int(item.get("member_id", 0)))
                role = guild.get_role(int(item.get("role_id", 0)))
                if member and role and role in member.roles and guild.me and role < guild.me.top_role:
                    try:
                        await member.remove_roles(role, reason="Temporary role expired")
                    except (discord.Forbidden, discord.HTTPException):
                        remaining_roles.append(item)
                        continue
                changed_roles = True
            if changed_roles:
                await self.bot.db.set_settings_value(guild.id, "temporary_roles", remaining_roles, self.bot.settings.default_prefix)

    @process_timers.before_loop
    async def before_process_timers(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Engagement(bot))
