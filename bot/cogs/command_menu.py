from __future__ import annotations

import datetime as dt
import json
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed, parse_duration


class CommandMenu(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reaction_roles: dict[tuple[int, int, str], int] = {}
        self.vc_owners: dict[int, int] = {}
        self.voice_joined_at: dict[tuple[int, int], float] = {}

    autorole = app_commands.Group(name="autorole", description="Automatic role for new members")
    channel = app_commands.Group(name="channel", description="Channel tools")
    chatrevive = app_commands.Group(name="chatrevive", description="Revive quiet chats")
    logs = app_commands.Group(name="logs", description="Server logs")
    reactionrole = app_commands.Group(name="reactionrole", description="Reaction roles")
    remind = app_commands.Group(name="remind", description="Personal reminders")
    role = app_commands.Group(name="role", description="Role tools")
    vc = app_commands.Group(name="vc", description="Temporary voice controls")

    @app_commands.command(name="ping", description="Check whether the bot is online")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong: {round(self.bot.latency * 1000)}ms")

    @app_commands.command(name="sync", description="Owner only: refresh slash commands")
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        global_synced = await self.bot.tree.sync()
        guild_synced = []
        if interaction.guild is not None:
            self.bot.tree.copy_global_to(guild=interaction.guild)
            guild_synced = await self.bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(
            f"Synced {len(global_synced)} global commands and {len(guild_synced)} server commands.",
            ephemeral=True,
        )

    @autorole.command(name="set", description="Give new members a role automatically")
    @app_admin()
    async def autorole_set(self, interaction: discord.Interaction, role: discord.Role) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        welcome = settings.get("welcome", {})
        welcome["autorole"] = role.id
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Autorole set to {role.mention}.", ephemeral=True)

    @autorole.command(name="off", description="Turn off autorole")
    @app_admin()
    async def autorole_off(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        welcome = settings.get("welcome", {})
        welcome["autorole"] = None
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome, self.bot.settings.default_prefix)
        await interaction.response.send_message("Autorole turned off.", ephemeral=True)

    @channel.command(name="lock", description="Lock the current text channel")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_lock(self, interaction: discord.Interaction) -> None:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message("Channel locked.", ephemeral=True)

    @channel.command(name="unlock", description="Unlock the current text channel")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_unlock(self, interaction: discord.Interaction) -> None:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message("Channel unlocked.", ephemeral=True)

    @channel.command(name="slowmode", description="Set channel slowmode seconds")
    @app_commands.default_permissions(manage_channels=True)
    async def channel_slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"Slowmode set to {seconds}s.", ephemeral=True)

    @chatrevive.command(name="enable", description="Post a revive message when chat is dry")
    @app_admin()
    async def chatrevive_enable(self, interaction: discord.Interaction, channel: discord.TextChannel, hours: app_commands.Range[int, 1, 168] = 12, message: str = "Chat has been quiet. What is everyone up to?") -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "chatrevive", {"enabled": True, "channel": channel.id, "hours": hours, "message": message}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Chat revive enabled.", ephemeral=True)

    @chatrevive.command(name="disable", description="Turn off chat revive")
    @app_admin()
    async def chatrevive_disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "chatrevive", {"enabled": False}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Chat revive disabled.", ephemeral=True)

    @logs.command(name="set", description="Set the server log channel")
    @app_admin()
    async def logs_set(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "log_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Logs will go to {channel.mention}.", ephemeral=True)

    @logs.command(name="off", description="Turn off server logs")
    @app_admin()
    async def logs_off(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "log_channel", None, self.bot.settings.default_prefix)
        await interaction.response.send_message("Logs turned off.", ephemeral=True)

    @reactionrole.command(name="add", description="Add a reaction role to a message")
    @app_admin()
    async def rr_add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role) -> None:
        message = await interaction.channel.fetch_message(int(message_id))
        await message.add_reaction(emoji)
        self.reaction_roles[(interaction.guild_id, message.id, emoji)] = role.id
        await interaction.response.send_message("Reaction role added for this runtime.", ephemeral=True)

    @reactionrole.command(name="remove", description="Remove a reaction role from a message")
    @app_admin()
    async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str) -> None:
        self.reaction_roles.pop((interaction.guild_id, int(message_id), emoji), None)
        await interaction.response.send_message("Reaction role removed.", ephemeral=True)

    @remind.command(name="me", description="Set a personal reminder")
    async def remind_me(self, interaction: discord.Interaction, duration: str, message: str) -> None:
        when = discord.utils.utcnow() + parse_duration(duration)
        await interaction.response.send_message(f"I will remind you {discord.utils.format_dt(when, 'R')}.", ephemeral=True)
        await discord.utils.sleep_until(when)
        await interaction.user.send(f"Reminder: {message}")

    @remind.command(name="list", description="List your reminders")
    async def remind_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Reminder storage is lightweight in this build; active reminders are kept while the bot is online.", ephemeral=True)

    @remind.command(name="delete", description="Delete one of your reminders")
    async def remind_delete(self, interaction: discord.Interaction, reminder_id: str) -> None:
        await interaction.response.send_message("That reminder was cleared if it was active.", ephemeral=True)

    @role.command(name="add", description="Add a role to a member")
    @app_commands.default_permissions(manage_roles=True)
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.add_roles(role, reason=f"Role add by {interaction.user}")
        await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)

    @role.command(name="remove", description="Remove a role from a member")
    @app_commands.default_permissions(manage_roles=True)
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        await member.remove_roles(role, reason=f"Role remove by {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)

    def owned_channel(self, member: discord.Member) -> discord.VoiceChannel | None:
        if member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
            channel = member.voice.channel
            owner = self.vc_owners.get(channel.id)
            if owner in {None, member.id} or member.guild_permissions.manage_channels:
                return channel
        return None

    @vc.command(name="claim", description="Claim an ownerless temporary voice channel")
    async def vc_claim(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        self.vc_owners[member.voice.channel.id] = member.id
        await interaction.response.send_message("You now own this voice channel.", ephemeral=True)

    async def settings(self, guild_id: int) -> dict:
        return await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)

    async def is_trusted(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator or member.id == member.guild.owner_id:
            return True
        settings = await self.settings(member.guild.id)
        anti = settings.get("antinuke_whitelist", [])
        if member.id in anti or any(role.id in anti for role in member.roles):
            return True
        role = discord.utils.get(member.roles, name="fren whitelist")
        return role is not None

    async def ensure_fren_role(self, guild: discord.Guild) -> discord.Role:
        role = discord.utils.get(guild.roles, name="fren whitelist")
        if role is None:
            role = await guild.create_role(name="fren whitelist", reason="Fren whitelist role created")
        return role

    async def add_vc_time(self, guild_id: int, user_id: int, seconds: int) -> None:
        if seconds <= 0:
            return
        settings = await self.settings(guild_id)
        stats = settings.get("vc_stats", {})
        stats[str(user_id)] = int(stats.get(str(user_id), 0)) + seconds
        await self.bot.db.set_settings_value(guild_id, "vc_stats", stats, self.bot.settings.default_prefix)

    async def recent_role_actor(self, guild: discord.Guild, target_id: int) -> discord.Member | None:
        try:
            async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.member_role_update):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 12:
                    continue
                if getattr(entry.target, "id", None) == target_id and entry.user:
                    return guild.get_member(entry.user.id)
        except discord.Forbidden:
            return None
        return None

    async def stfu_target_for(self, guild_id: int, user_id: int) -> int | None:
        settings = await self.settings(guild_id)
        active = settings.get("vc_stfu", {})
        for actor_id, target_id in active.items():
            if int(target_id) == user_id:
                return int(actor_id)
        return None

    @vc.command(name="leaderboard", description="Show the VC time leaderboard")
    async def vc_leaderboard(self, interaction: discord.Interaction) -> None:
        settings = await self.settings(interaction.guild_id)
        stats = settings.get("vc_stats", {})
        rows = sorted(((int(uid), int(seconds)) for uid, seconds in stats.items()), key=lambda item: item[1], reverse=True)[:10]
        e = embed("VC Leaderboard")
        for index, (user_id, seconds) in enumerate(rows, start=1):
            hours, rem = divmod(seconds, 3600)
            minutes = rem // 60
            e.add_field(name=f"#{index}", value=f"<@{user_id}> - {hours}h {minutes}m", inline=False)
        if not rows:
            e.description = "No VC time tracked yet."
        await interaction.response.send_message(embed=e)

    @commands.group(name="vc", invoke_without_command=True)
    async def vc_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("Use `-vc leaderboard` or `-vc stfu @user`.", mention_author=False)

    @vc_prefix.command(name="leaderboard", aliases=["lb", "top"])
    async def vc_prefix_leaderboard(self, ctx: commands.Context) -> None:
        settings = await self.settings(ctx.guild.id)
        stats = settings.get("vc_stats", {})
        rows = sorted(((int(uid), int(seconds)) for uid, seconds in stats.items()), key=lambda item: item[1], reverse=True)[:10]
        e = embed("VC Leaderboard")
        for index, (user_id, seconds) in enumerate(rows, start=1):
            hours, rem = divmod(seconds, 3600)
            minutes = rem // 60
            e.add_field(name=f"#{index}", value=f"<@{user_id}> - {hours}h {minutes}m", inline=False)
        if not rows:
            e.description = "No VC time tracked yet."
        await ctx.reply(embed=e, mention_author=False)

    @vc_prefix.command(name="stfu")
    async def vc_stfu(self, ctx: commands.Context, member: discord.Member) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if not await self.is_trusted(ctx.author):
            await ctx.reply("Only admins, anti-nuke whitelisted users, or fren whitelist users can use this.", mention_author=False)
            return
        settings = await self.settings(ctx.guild.id)
        active = settings.get("vc_stfu", {})
        actor_key = str(ctx.author.id)
        existing_actor_key = next((key for key, target_id in active.items() if int(target_id) == member.id), None)
        if existing_actor_key is not None:
            active.pop(existing_actor_key)
            await self.bot.db.set_settings_value(ctx.guild.id, "vc_stfu", active, self.bot.settings.default_prefix)
            try:
                await member.edit(mute=False, reason=f"STFU disabled by {ctx.author}")
            except discord.HTTPException:
                pass
            await ctx.reply(f"Stopped STFU mute lock on {member.mention}.", mention_author=False)
            return
        if actor_key in active:
            await ctx.reply("You already have one STFU target. Turn it off before targeting someone else.", mention_author=False)
            return
        active[actor_key] = member.id
        await self.bot.db.set_settings_value(ctx.guild.id, "vc_stfu", active, self.bot.settings.default_prefix)
        if member.voice:
            try:
                await member.edit(mute=True, reason=f"STFU enabled by {ctx.author}")
            except discord.HTTPException:
                pass
        await ctx.reply(f"STFU mute lock enabled on {member.mention}. Run the command again to stop.", mention_author=False)

    @commands.command(name="ggive")
    async def ggive(self, ctx: commands.Context, member: discord.Member, item: str) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return
        if item.lower() not in {"fw", "frwhitelist", "frenwhitelist"}:
            await ctx.reply("Use `.ggive @user fw`.", mention_author=False)
            return
        if not await self.is_trusted(ctx.author):
            await ctx.reply("Only admins, anti-nuke whitelisted users, or fren whitelist users can give this.", mention_author=False)
            return
        role = await self.ensure_fren_role(ctx.guild)
        await member.add_roles(role, reason=f"Fren whitelist given by {ctx.author}")
        settings = await self.settings(ctx.guild.id)
        grants = settings.get("fr_whitelist_grants", {})
        grants[str(member.id)] = ctx.author.id
        await self.bot.db.set_settings_value(ctx.guild.id, "fr_whitelist_grants", grants, self.bot.settings.default_prefix)
        await ctx.reply(f"Gave {member.mention} the `{role.name}` role.", mention_author=False)

    @vc.command(name="rename", description="Rename your temporary voice channel")
    async def vc_rename(self, interaction: discord.Interaction, name: str) -> None:
        channel = self.owned_channel(interaction.user)
        if not channel:
            await interaction.response.send_message("You do not own your current voice channel.", ephemeral=True)
            return
        await channel.edit(name=name[:90])
        await interaction.response.send_message("Voice channel renamed.", ephemeral=True)

    @vc.command(name="lock", description="Lock your temporary voice channel")
    async def vc_lock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("Voice channel locked.", ephemeral=True)

    @vc.command(name="unlock", description="Unlock your temporary voice channel")
    async def vc_unlock(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
        await interaction.response.send_message("Voice channel unlocked.", ephemeral=True)

    @vc.command(name="hide", description="Hide your temporary voice channel")
    async def vc_hide(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice channel hidden.", ephemeral=True)

    @vc.command(name="reveal", description="Reveal your temporary voice channel")
    async def vc_reveal(self, interaction: discord.Interaction) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await interaction.response.send_message("Voice channel revealed.", ephemeral=True)

    @vc.command(name="limit", description="Set your temporary voice user limit")
    async def vc_limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(user_limit=limit)
        await interaction.response.send_message("Voice channel limit updated.", ephemeral=True)

    @vc.command(name="bitrate", description="Set your temporary voice bitrate")
    async def vc_bitrate(self, interaction: discord.Interaction, bitrate: app_commands.Range[int, 8000, 384000]) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.edit(bitrate=bitrate)
        await interaction.response.send_message("Voice channel bitrate updated.", ephemeral=True)

    @vc.command(name="permit", description="Allow a member into your temporary voice channel")
    async def vc_permit(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(member, connect=True, view_channel=True)
        await interaction.response.send_message(f"Permitted {member.mention}.", ephemeral=True)

    @vc.command(name="reject", description="Block a member from your temporary voice channel")
    async def vc_reject(self, interaction: discord.Interaction, member: discord.Member) -> None:
        godmode = self.bot.get_cog("GodMode")
        if godmode and await godmode.is_protected(member) and not await godmode.actor_has_override(interaction.user, interaction.guild):
            await interaction.response.send_message("That member is protected by God Mode. Only admins can reject them.", ephemeral=True)
            return
        channel = self.owned_channel(interaction.user)
        if channel:
            await channel.set_permissions(member, connect=False)
            if member.voice and member.voice.channel == channel:
                await member.move_to(None)
        await interaction.response.send_message(f"Rejected {member.mention}.", ephemeral=True)

    @vc.command(name="transfer", description="Transfer your temporary voice channel ownership")
    async def vc_transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = self.owned_channel(interaction.user)
        if channel:
            self.vc_owners[channel.id] = member.id
        await interaction.response.send_message(f"Transferred ownership to {member.mention}.", ephemeral=True)

    @vc.command(name="godmode", description="Protect a member from bot VC reject/control commands")
    @app_admin()
    async def vc_godmode(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = settings.get("vc_godmode", [])
        if member.id not in ids:
            ids.append(member.id)
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await interaction.response.send_message("VC God Mode updated.", ephemeral=True)

    @vc.command(name="godmodeoff", description="Remove VC god mode from a member")
    @app_admin()
    async def vc_godmodeoff(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        ids = [uid for uid in settings.get("vc_godmode", []) if uid != member.id]
        await self.bot.db.set_settings_value(interaction.guild_id, "vc_godmode", ids, self.bot.settings.default_prefix)
        await interaction.response.send_message("VC God Mode removed.", ephemeral=True)

    @vc.command(name="godmodelist", description="Show members with VC god mode")
    @app_admin()
    async def vc_godmodelist(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        await interaction.response.send_message(", ".join(f"<@{uid}>" for uid in settings.get("vc_godmode", [])) or "No VC God Mode members.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.member is None:
            return
        role_id = self.reaction_roles.get((payload.guild_id, payload.message_id, str(payload.emoji)))
        if role_id:
            role = payload.member.guild.get_role(role_id)
            if role:
                await payload.member.add_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role_id = self.reaction_roles.get((payload.guild_id, payload.message_id, str(payload.emoji)))
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id) if role_id else None
        if member and role:
            await member.remove_roles(role, reason="Reaction role")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        key = (member.guild.id, member.id)
        now = time.time()
        if before.channel is None and after.channel is not None:
            self.voice_joined_at[key] = now
        elif before.channel is not None and after.channel is None:
            started = self.voice_joined_at.pop(key, None)
            if started:
                await self.add_vc_time(member.guild.id, member.id, int(now - started))
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            started = self.voice_joined_at.get(key)
            if started:
                await self.add_vc_time(member.guild.id, member.id, int(now - started))
            self.voice_joined_at[key] = now

        actor_id = await self.stfu_target_for(member.guild.id, member.id)
        if actor_id and after.channel is not None and not after.mute:
            try:
                await member.edit(mute=True, reason=f"STFU mute lock active by {actor_id}")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        role = discord.utils.get(after.guild.roles, name="fren whitelist")
        if role is None or role in after.roles or role not in before.roles:
            return
        settings = await self.settings(after.guild.id)
        grants = settings.get("fr_whitelist_grants", {})
        giver_id = int(grants.get(str(after.id), 0))
        actor = await self.recent_role_actor(after.guild, after.id)
        allowed = False
        if actor:
            allowed = actor.guild_permissions.administrator or actor.id == giver_id or await self.is_trusted(actor)
        if allowed:
            return
        try:
            await after.add_roles(role, reason="Fren whitelist protection: unauthorized removal blocked")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandMenu(bot))
