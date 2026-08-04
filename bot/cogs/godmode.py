from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin


class GodMode(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    godmode = app_commands.Group(name="godmode", description="Manage protected users and roles")

    async def is_protected(self, member: discord.Member) -> bool:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        data = settings.get("godmode", {"users": [], "roles": []})
        vc_ids = settings.get("vc_godmode", [])
        return (
            member.id in data.get("users", [])
            or member.id in vc_ids
            or any(role.id in data.get("roles", []) for role in member.roles)
        )

    async def actor_has_override(self, actor: discord.Member | discord.User | None, guild: discord.Guild) -> bool:
        if actor is None:
            return False
        if actor.id == guild.owner_id or await self.bot.is_owner(actor):
            return True
        member = actor if isinstance(actor, discord.Member) else guild.get_member(actor.id)
        return bool(member and member.guild_permissions.administrator)

    async def recent_actor(self, guild: discord.Guild, target_id: int, actions: list[discord.AuditLogAction], delay: float = 1.0) -> discord.Member | discord.User | None:
        if delay > 0:
            await asyncio.sleep(delay)
        for action in actions:
            try:
                async for entry in guild.audit_logs(limit=6, action=action):
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() > 12:
                        continue
                    if getattr(entry.target, "id", None) == target_id or action in {
                        getattr(discord.AuditLogAction, "member_disconnect", None),
                        getattr(discord.AuditLogAction, "member_move", None),
                    }:
                        return entry.user
            except discord.Forbidden:
                return None
        return None

    @godmode.command(name="add_user", description="Protect a user from moderator actions")
    @app_admin()
    async def add_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._add(interaction, "users", member.id)

    @godmode.command(name="add_role", description="Protect a role from moderator actions")
    @app_admin()
    async def add_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self._add(interaction, "roles", role.id)

    @godmode.command(name="remove_user", description="Remove user protection")
    @app_admin()
    async def remove_user(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await self._remove(interaction, "users", member.id)

    @godmode.command(name="remove_role", description="Remove role protection")
    @app_admin()
    async def remove_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self._remove(interaction, "roles", role.id)

    @commands.command(name="godmode")
    @commands.has_guild_permissions(administrator=True)
    async def prefix_godmode(self, ctx: commands.Context, action: str | None = None, target: discord.Member | discord.Role | None = None) -> None:
        """Prefix God Mode controls: add/remove a member or role."""
        if ctx.guild is None:
            return
        if action is None or target is None:
            await ctx.reply("Use `godmode add @member`, `godmode remove @member`, `godmode add @role`, or `godmode remove @role`.", mention_author=False)
            return
        action = action.lower()
        if action not in {"add", "remove"}:
            await ctx.reply("Use `add` or `remove`.", mention_author=False)
            return
        key = "roles" if isinstance(target, discord.Role) else "users"
        settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
        data = settings.get("godmode", {"users": [], "roles": []})
        values = data.setdefault(key, [])
        if action == "add":
            if target.id not in values:
                values.append(target.id)
            message = f"God Mode added for {target.mention}."
        else:
            data[key] = [item for item in values if item != target.id]
            message = f"God Mode removed for {target.mention}."
        await self.bot.db.set_settings_value(ctx.guild.id, "godmode", data, self.bot.settings.default_prefix)
        await ctx.reply(message, mention_author=False)

    async def _add(self, interaction: discord.Interaction, key: str, value: int) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("godmode", {"users": [], "roles": []})
        if value not in data.setdefault(key, []):
            data[key].append(value)
        await self.bot.db.set_settings_value(interaction.guild_id, "godmode", data, self.bot.settings.default_prefix)
        await interaction.response.send_message("God Mode updated.", ephemeral=True)

    async def _remove(self, interaction: discord.Interaction, key: str, value: int) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("godmode", {"users": [], "roles": []})
        data[key] = [item for item in data.get(key, []) if item != value]
        await self.bot.db.set_settings_value(interaction.guild_id, "godmode", data, self.bot.settings.default_prefix)
        await interaction.response.send_message("God Mode updated.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not await self.is_protected(after):
            return
        timeout_added = before.timed_out_until != after.timed_out_until and after.timed_out_until is not None
        if not timeout_added:
            return
        actor = await self.recent_actor(after.guild, after.id, [discord.AuditLogAction.member_update])
        if await self.actor_has_override(actor, after.guild):
            return
        try:
            await after.timeout(None, reason="God Mode protection: timeout blocked")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot or not await self.is_protected(member):
            return
        server_muted = not before.mute and after.mute
        server_deafened = not before.deaf and after.deaf
        disconnected = before.channel is not None and after.channel is None
        moved = before.channel is not None and after.channel is not None and before.channel.id != after.channel.id
        if not any((server_muted, server_deafened, disconnected, moved)):
            return
        actions = [discord.AuditLogAction.member_update]
        if hasattr(discord.AuditLogAction, "member_disconnect"):
            actions.append(discord.AuditLogAction.member_disconnect)
        if hasattr(discord.AuditLogAction, "member_move"):
            actions.append(discord.AuditLogAction.member_move)
        actor = await self.recent_actor(member.guild, member.id, actions, delay=0)
        if await self.actor_has_override(actor, member.guild):
            return
        try:
            if server_muted or server_deafened:
                await member.edit(mute=False if server_muted else after.mute, deafen=False if server_deafened else after.deaf, reason="God Mode protection: voice mute/deafen blocked")
            if (disconnected or moved) and before.channel is not None:
                await member.move_to(before.channel, reason="God Mode protection: disconnect/move blocked")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GodMode(bot))
