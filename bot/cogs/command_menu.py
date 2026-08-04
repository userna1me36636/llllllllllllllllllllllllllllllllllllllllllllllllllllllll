from __future__ import annotations

import datetime as dt
import json

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner
from bot.core.utils import embed, parse_duration


class CommandMenu(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.reaction_roles: dict[tuple[int, int, str], int] = {}
        self.vc_owners: dict[int, int] = {}

    autorole = app_commands.Group(name="autorole", description="Automatic role for new members")
    channel = app_commands.Group(name="channel", description="Channel tools")
    chatrevive = app_commands.Group(name="chatrevive", description="Revive quiet chats")
    logs = app_commands.Group(name="logs", description="Server logs")
    ownerrole = app_commands.Group(
        name="ownerrole",
        description="Owner-only high role tools",
        default_permissions=discord.Permissions(administrator=True),
    )
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

    async def owner_role_allowed(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        if await configured_owner(self.bot, interaction.user):
            return True
        await interaction.response.send_message("Only users listed in OWNER_IDS can use this command.", ephemeral=True)
        return False

    async def bot_can_manage_role(self, interaction: discord.Interaction, role: discord.Role) -> bool:
        me = interaction.guild.me if interaction.guild else None
        if me is None:
            await interaction.response.send_message("I could not check my bot role.", ephemeral=True)
            return False
        if role.is_default() or role.managed:
            await interaction.response.send_message("I cannot manage that role.", ephemeral=True)
            return False
        if role >= me.top_role:
            await interaction.response.send_message("I cannot touch that role because it is higher than, or equal to, my highest bot role. Move my bot role above it first.", ephemeral=True)
            return False
        return True

    @ownerrole.command(name="add", description="OWNER_IDS only: add a role using the bot's role height")
    async def ownerrole_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await member.add_roles(role, reason=f"Owner role add by {interaction.user}")
        await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)

    @ownerrole.command(name="remove", description="OWNER_IDS only: remove a role using the bot's role height")
    async def ownerrole_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        await member.remove_roles(role, reason=f"Owner role remove by {interaction.user}")
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)

    @ownerrole.command(name="move_above", description="OWNER_IDS only: move a role above another role")
    async def ownerrole_move_above(self, interaction: discord.Interaction, role: discord.Role, above_role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        if not await self.bot_can_manage_role(interaction, above_role):
            return
        max_position = interaction.guild.me.top_role.position - 1
        position = min(above_role.position + 1, max_position)
        await role.edit(position=position, reason=f"Owner role move by {interaction.user}")
        await interaction.response.send_message(f"Moved {role.mention} above {above_role.mention}.", ephemeral=True)

    @ownerrole.command(name="move_below", description="OWNER_IDS only: move a role below another role")
    async def ownerrole_move_below(self, interaction: discord.Interaction, role: discord.Role, below_role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        if not await self.bot_can_manage_role(interaction, below_role):
            return
        await role.edit(position=below_role.position, reason=f"Owner role move by {interaction.user}")
        await interaction.response.send_message(f"Moved {role.mention} below {below_role.mention}.", ephemeral=True)

    @ownerrole.command(name="move_top", description="OWNER_IDS only: move a role as high as the bot can")
    async def ownerrole_move_top(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        position = interaction.guild.me.top_role.position - 1
        await role.edit(position=position, reason=f"Owner role move top by {interaction.user}")
        await interaction.response.send_message(f"Moved {role.mention} as high as I can place it.", ephemeral=True)

    async def set_role_admin(self, interaction: discord.Interaction, role: discord.Role, enabled: bool) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        permissions = role.permissions
        if permissions.administrator == enabled:
            state = "already has" if enabled else "already does not have"
            await interaction.response.send_message(f"{role.mention} {state} Administrator.", ephemeral=True)
            return
        permissions.administrator = enabled
        await role.edit(permissions=permissions, reason=f"Owner role admin {'enabled' if enabled else 'disabled'} by {interaction.user}")
        state = "gave Administrator to" if enabled else "removed Administrator from"
        await interaction.response.send_message(f"I {state} {role.mention}.", ephemeral=True)

    @ownerrole.command(name="admin_on", description="OWNER_IDS only: give Administrator to a role")
    async def ownerrole_admin_on(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.set_role_admin(interaction, role, True)

    @ownerrole.command(name="admin_off", description="OWNER_IDS only: remove Administrator from a role")
    async def ownerrole_admin_off(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.set_role_admin(interaction, role, False)

    @ownerrole.command(name="admin_toggle", description="OWNER_IDS only: toggle Administrator on a role")
    async def ownerrole_admin_toggle(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if not await self.owner_role_allowed(interaction):
            return
        if not await self.bot_can_manage_role(interaction, role):
            return
        permissions = role.permissions
        permissions.administrator = not permissions.administrator
        await role.edit(permissions=permissions, reason=f"Owner role admin toggled by {interaction.user}")
        state = "on" if permissions.administrator else "off"
        await interaction.response.send_message(f"Administrator is now `{state}` for {role.mention}.", ephemeral=True)

    async def prefix_owner_role_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False
        if await configured_owner(self.bot, ctx.author):
            return True
        await ctx.reply("Only users listed in OWNER_IDS can use this command.", mention_author=False)
        return False

    async def prefix_bot_can_manage_role(self, ctx: commands.Context, role: discord.Role) -> bool:
        me = ctx.guild.me if ctx.guild else None
        if me is None:
            await ctx.reply("I could not check my bot role.", mention_author=False)
            return False
        if role.is_default() or role.managed:
            await ctx.reply("I cannot manage that role.", mention_author=False)
            return False
        if role >= me.top_role:
            await ctx.reply("I cannot touch that role because it is higher than, or equal to, my highest bot role. Move my bot role above it first.", mention_author=False)
            return False
        return True

    @commands.group(name="ownerrole", aliases=["orole"], hidden=True, invoke_without_command=True)
    async def ownerrole_prefix(self, ctx: commands.Context) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        await ctx.reply("Use `ownerrole add @member @role`, `ownerrole remove @member @role`, `ownerrole move_top @role`, `ownerrole move_above @role @otherrole`, `ownerrole move_below @role @otherrole`, or the admin commands.", mention_author=False)

    @ownerrole_prefix.command(name="add")
    async def ownerrole_prefix_add(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        await member.add_roles(role, reason=f"Owner role add by {ctx.author}")
        await ctx.reply(f"Added {role.mention} to {member.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="remove")
    async def ownerrole_prefix_remove(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        await member.remove_roles(role, reason=f"Owner role remove by {ctx.author}")
        await ctx.reply(f"Removed {role.mention} from {member.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="move_above", aliases=["moveabove"])
    async def ownerrole_prefix_move_above(self, ctx: commands.Context, role: discord.Role, above_role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        if not await self.prefix_bot_can_manage_role(ctx, role) or not await self.prefix_bot_can_manage_role(ctx, above_role):
            return
        max_position = ctx.guild.me.top_role.position - 1
        position = min(above_role.position + 1, max_position)
        await role.edit(position=position, reason=f"Owner role move by {ctx.author}")
        await ctx.reply(f"Moved {role.mention} above {above_role.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="move_below", aliases=["movebelow"])
    async def ownerrole_prefix_move_below(self, ctx: commands.Context, role: discord.Role, below_role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx):
            return
        if not await self.prefix_bot_can_manage_role(ctx, role) or not await self.prefix_bot_can_manage_role(ctx, below_role):
            return
        await role.edit(position=below_role.position, reason=f"Owner role move by {ctx.author}")
        await ctx.reply(f"Moved {role.mention} below {below_role.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="move_top", aliases=["movetop"])
    async def ownerrole_prefix_move_top(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        position = ctx.guild.me.top_role.position - 1
        await role.edit(position=position, reason=f"Owner role move top by {ctx.author}")
        await ctx.reply(f"Moved {role.mention} as high as I can place it.", mention_author=False)

    @ownerrole_prefix.command(name="admin_on", aliases=["adminon"])
    async def ownerrole_prefix_admin_on(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = True
        await role.edit(permissions=permissions, reason=f"Owner role admin enabled by {ctx.author}")
        await ctx.reply(f"I gave Administrator to {role.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="admin_off", aliases=["adminoff"])
    async def ownerrole_prefix_admin_off(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = False
        await role.edit(permissions=permissions, reason=f"Owner role admin disabled by {ctx.author}")
        await ctx.reply(f"I removed Administrator from {role.mention}.", mention_author=False)

    @ownerrole_prefix.command(name="admin_toggle", aliases=["admintoggle"])
    async def ownerrole_prefix_admin_toggle(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.prefix_owner_role_allowed(ctx) or not await self.prefix_bot_can_manage_role(ctx, role):
            return
        permissions = role.permissions
        permissions.administrator = not permissions.administrator
        await role.edit(permissions=permissions, reason=f"Owner role admin toggled by {ctx.author}")
        state = "on" if permissions.administrator else "off"
        await ctx.reply(f"Administrator is now `{state}` for {role.mention}.", mention_author=False)

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommandMenu(bot))
