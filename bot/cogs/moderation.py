from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import configured_owner, has_guild_permissions
from bot.core.utils import embed, parse_duration


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


    async def protected(self, guild_id: int, target: discord.Member, actor: discord.Member) -> bool:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        gm = settings.get("godmode", {})
        if target.id in getattr(self.bot.settings, "owner_ids", set()) and not await configured_owner(self.bot, actor):
            return True
        if actor.guild_permissions.administrator or actor.id == target.guild.owner_id:
            return False
        return target.id in gm.get("users", []) or any(role.id in gm.get("roles", []) for role in target.roles)

    async def case(self, guild_id: int, user_id: int, mod_id: int, action: str, reason: str | None = None, expires_at: str | None = None) -> int:
        return await self.bot.db.execute(
            "INSERT INTO cases(guild_id,user_id,moderator_id,action,reason,expires_at) VALUES(?,?,?,?,?,?)",
            guild_id, user_id, mod_id, action, reason, expires_at,
        )

    async def get_foreverbans(self, guild_id: int) -> dict[str, dict[str, str | int]]:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("foreverbans", {})

    async def save_foreverbans(self, guild_id: int, foreverbans: dict[str, dict[str, str | int]]) -> None:
        await self.bot.db.set_settings_value(guild_id, "foreverbans", foreverbans, self.bot.settings.default_prefix)

    async def set_all_channel_locks(self, guild: discord.Guild, locked: bool, reason: str) -> tuple[int, int]:
        changed = 0
        skipped = 0
        for channel in guild.text_channels:
            if guild.me is None or not channel.permissions_for(guild.me).manage_channels:
                skipped += 1
                continue
            try:
                await channel.set_permissions(guild.default_role, send_messages=False if locked else None, reason=reason)
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                skipped += 1
        return changed, skipped

    @commands.hybrid_command(name="ban")
    @has_guild_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected by God Mode.", mention_author=False)
            return
        await member.ban(reason=reason, delete_message_days=0)
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        await ctx.reply(embed=embed("Banned", f"{member.mention} was banned.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="kick")
    @has_guild_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected by God Mode.", mention_author=False)
            return
        await member.kick(reason=reason)
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "kick", reason)
        await ctx.reply(embed=embed("Kicked", f"{member.mention} was kicked.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="softban")
    @has_guild_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        if await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected.", mention_author=False)
            return
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.guild.unban(member, reason="Softban release")
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "softban", reason)
        await ctx.reply(embed=embed("Softbanned", f"{member} was softbanned.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="tempban")
    @has_guild_permissions(ban_members=True)
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided") -> None:
        if await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected.", mention_author=False)
            return
        delta = parse_duration(duration)
        expires = discord.utils.utcnow() + delta
        await member.ban(reason=reason)
        await self.bot.db.execute("INSERT INTO temp_actions(guild_id,user_id,action,expires_at) VALUES(?,?,?,?)", ctx.guild.id, member.id, "unban", expires.timestamp())
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "tempban", reason, expires.isoformat())
        await ctx.reply(embed=embed("Tempbanned", f"{member} until {discord.utils.format_dt(expires)}.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_group(name="foreverban", invoke_without_command=True)
    @has_guild_permissions(ban_members=True)
    async def foreverban(self, ctx: commands.Context, user: discord.User, *, reason: str = "Forever banned") -> None:
        if ctx.guild is None:
            return
        member = ctx.guild.get_member(user.id)
        if member and await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected.", mention_author=False)
            return
        foreverbans = await self.get_foreverbans(ctx.guild.id)
        foreverbans[str(user.id)] = {"reason": reason, "moderator_id": ctx.author.id}
        await self.save_foreverbans(ctx.guild.id, foreverbans)
        await ctx.guild.ban(user, reason=f"Foreverban by {ctx.author}: {reason}", delete_message_days=0)
        case_id = await self.case(ctx.guild.id, user.id, ctx.author.id, "foreverban", reason)
        await ctx.reply(embed=embed("Forever Banned", f"{user.mention} will be banned again if unbanned or if they rejoin.\nCase `#{case_id}`"), mention_author=False)

    @foreverban.command(name="remove")
    @has_guild_permissions(ban_members=True)
    async def foreverban_remove(self, ctx: commands.Context, user_id: int) -> None:
        foreverbans = await self.get_foreverbans(ctx.guild.id)
        foreverbans.pop(str(user_id), None)
        await self.save_foreverbans(ctx.guild.id, foreverbans)
        await ctx.reply(f"Foreverban removed for `{user_id}`.", mention_author=False)

    @foreverban.command(name="list")
    @has_guild_permissions(ban_members=True)
    async def foreverban_list(self, ctx: commands.Context) -> None:
        foreverbans = await self.get_foreverbans(ctx.guild.id)
        e = embed("Foreverban List")
        if not foreverbans:
            e.description = "No foreverbans set."
        for user_id, data in list(foreverbans.items())[:20]:
            e.add_field(name=user_id, value=str(data.get("reason", "No reason"))[:300], inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @commands.hybrid_command(name="unban")
    @has_guild_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided") -> None:
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        case_id = await self.case(ctx.guild.id, user_id, ctx.author.id, "unban", reason)
        await ctx.reply(embed=embed("Unbanned", f"{user} was unbanned.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="timeout")
    @has_guild_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason provided") -> None:
        if await self.protected(ctx.guild.id, member, ctx.author):
            await ctx.reply("That member is protected by God Mode.", mention_author=False)
            return
        until = discord.utils.utcnow() + parse_duration(duration)
        await member.timeout(until, reason=reason)
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "timeout", reason, until.isoformat())
        await ctx.reply(embed=embed("Timed Out", f"{member.mention} until {discord.utils.format_dt(until)}.\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="untimeout")
    @has_guild_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        await member.timeout(None, reason=reason)
        case_id = await self.case(ctx.guild.id, member.id, ctx.author.id, "untimeout", reason)
        await ctx.reply(embed=embed("Timeout Removed", f"{member.mention}\nCase `#{case_id}`"), mention_author=False)

    @commands.hybrid_command(name="warn")
    @has_guild_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided") -> None:
        warn_id = await self.bot.db.execute("INSERT INTO warnings(guild_id,user_id,moderator_id,reason) VALUES(?,?,?,?)", ctx.guild.id, member.id, ctx.author.id, reason)
        await self.case(ctx.guild.id, member.id, ctx.author.id, "warn", reason)
        await ctx.reply(embed=embed("Warned", f"{member.mention} received warning `#{warn_id}`."), mention_author=False)

    @commands.hybrid_command(name="warnings")
    @has_guild_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member) -> None:
        rows = await self.bot.db.fetchall("SELECT id, moderator_id, reason, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10", ctx.guild.id, member.id)
        e = embed("Warning History", member.mention)
        for row in rows:
            e.add_field(name=f"#{row['id']} by {row['moderator_id']}", value=f"{row['reason']} | {row['created_at']}", inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @commands.hybrid_command(name="removewarn")
    @has_guild_permissions(moderate_members=True)
    async def remove_warn(self, ctx: commands.Context, warn_id: int) -> None:
        await self.bot.db.execute("DELETE FROM warnings WHERE guild_id=? AND id=?", ctx.guild.id, warn_id)
        await ctx.reply(f"Warning `#{warn_id}` removed.", mention_author=False)

    @commands.hybrid_command(name="purge")
    @has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: commands.Range[int, 1, 1000], member: discord.Member | None = None) -> None:
        def check(message: discord.Message) -> bool:
            return member is None or message.author.id == member.id
        deleted = await ctx.channel.purge(limit=amount, check=check, bulk=True)
        await ctx.reply(f"Deleted {len(deleted)} messages.", delete_after=5, mention_author=False)

    @commands.hybrid_command(name="slowmode")
    @has_guild_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: commands.Range[int, 0, 21600]) -> None:
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.reply(f"Slowmode set to {seconds}s.", mention_author=False)

    @commands.hybrid_command(name="nickname")
    @has_guild_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, nickname: str | None = None) -> None:
        await member.edit(nick=nickname)
        await ctx.reply("Nickname updated.", mention_author=False)

    @commands.command(name="role")
    @has_guild_permissions(manage_roles=True)
    async def role(self, ctx: commands.Context, action: str, member: discord.Member, role: discord.Role) -> None:
        action = action.lower()
        if action in {"add", "give"}:
            await member.add_roles(role, reason=f"Role command by {ctx.author}")
        elif action in {"remove", "take"}:
            await member.remove_roles(role, reason=f"Role command by {ctx.author}")
        else:
            await ctx.reply("Use `add` or `remove`.", mention_author=False)
            return
        await ctx.reply(f"Role updated for {member.mention}.", mention_author=False)

    @commands.hybrid_command(name="lock")
    @has_guild_permissions(manage_channels=True)
    @app_commands.describe(target="Use channel for this channel or all for every text channel")
    @app_commands.choices(target=[
        app_commands.Choice(name="This channel", value="channel"),
        app_commands.Choice(name="All channels", value="all"),
    ])
    async def lock(self, ctx: commands.Context, target: str = "channel") -> None:
        target = target.lower().strip()
        if target in {"all", "server", "every"}:
            changed, skipped = await self.set_all_channel_locks(ctx.guild, True, f"Lock all by {ctx.author}")
            await ctx.reply(f"Locked `{changed}` text channels. Skipped `{skipped}` channels I could not manage.", mention_author=False)
            return
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False, reason=f"Channel lock by {ctx.author}")
        await ctx.reply("This channel is locked.", mention_author=False)

    @commands.hybrid_command(name="unlock")
    @has_guild_permissions(manage_channels=True)
    @app_commands.describe(target="Use channel for this channel or all for every text channel")
    @app_commands.choices(target=[
        app_commands.Choice(name="This channel", value="channel"),
        app_commands.Choice(name="All channels", value="all"),
    ])
    async def unlock(self, ctx: commands.Context, target: str = "channel") -> None:
        target = target.lower().strip()
        if target in {"all", "server", "every"}:
            changed, skipped = await self.set_all_channel_locks(ctx.guild, False, f"Unlock all by {ctx.author}")
            await ctx.reply(f"Unlocked `{changed}` text channels. Skipped `{skipped}` channels I could not manage.", mention_author=False)
            return
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None, reason=f"Channel unlock by {ctx.author}")
        await ctx.reply("This channel is unlocked.", mention_author=False)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        foreverbans = await self.get_foreverbans(member.guild.id)
        data = foreverbans.get(str(member.id))
        if data:
            await member.ban(reason=f"Foreverban re-applied: {data.get('reason', 'No reason')}", delete_message_days=0)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        foreverbans = await self.get_foreverbans(guild.id)
        data = foreverbans.get(str(user.id))
        if data:
            try:
                await guild.ban(user, reason=f"Foreverban re-applied after unban: {data.get('reason', 'No reason')}", delete_message_days=0)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
