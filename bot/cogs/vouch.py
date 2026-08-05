from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import configured_owner
from bot.core.utils import embed


class Vouch(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    vouch_group = app_commands.Group(name="vouch", description="Vouch role and limit tools")

    async def is_config_owner(self, guild: discord.Guild | None, user: discord.abc.User | None) -> bool:
        if guild is None or user is None:
            return False
        return user.id == guild.owner_id or await configured_owner(self.bot, user)

    async def get_config(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("vouch", {"role_id": None, "limits": {}, "given": {}})

    async def save_config(self, guild_id: int, config: dict) -> None:
        await self.bot.db.set_settings_value(guild_id, "vouch", config, self.bot.settings.default_prefix)

    async def bot_can_give_role(self, guild: discord.Guild, role: discord.Role) -> str | None:
        me = guild.me
        if me is None:
            return "I could not check my bot role."
        if not me.guild_permissions.manage_roles:
            return "I need Manage Roles to give the vouch role."
        if role.is_default() or role.managed:
            return "I cannot give that role."
        if role >= me.top_role:
            return "The vouch role must be below my highest bot role."
        return None

    def limit_for_member(self, member: discord.Member, config: dict) -> int:
        limits = config.get("limits", {})
        best = 0
        for role in member.roles:
            best = max(best, int(limits.get(str(role.id), 0)))
        return best

    async def give_vouch(self, guild: discord.Guild, voucher: discord.Member, target: discord.Member) -> str:
        if target.bot:
            return "You cannot vouch bots."
        if target.id == voucher.id:
            return "You cannot vouch yourself."

        config = await self.get_config(guild.id)
        role_id = config.get("role_id")
        if not role_id:
            return "No vouch role is set yet. The server owner can use `vouch role @role`."

        role = guild.get_role(int(role_id))
        if role is None:
            return "The saved vouch role was deleted. Set it again."

        problem = await self.bot_can_give_role(guild, role)
        if problem:
            return problem

        is_owner = await self.is_config_owner(guild, voucher)
        limit = self.limit_for_member(voucher, config)
        if not is_owner and limit <= 0:
            return "Your roles do not have any vouches available."

        given = config.setdefault("given", {})
        voucher_targets = given.setdefault(str(voucher.id), [])
        if target.id in voucher_targets:
            return f"You already vouched {target.mention}."
        if not is_owner and len(voucher_targets) >= limit:
            return f"You used all your vouches. Your limit is `{limit}`."

        await target.add_roles(role, reason=f"Vouched by {voucher}")
        voucher_targets.append(target.id)
        await self.save_config(guild.id, config)
        used_text = "unlimited" if is_owner else f"{len(voucher_targets)}/{limit}"
        return f"{voucher.mention} vouched {target.mention} and gave {role.mention}. Used: `{used_text}`."

    def status_embed(self, guild: discord.Guild, config: dict) -> discord.Embed:
        role = guild.get_role(int(config["role_id"])) if config.get("role_id") else None
        e = embed("Vouch Settings")
        e.add_field(name="Vouch Role", value=role.mention if role else "Not set", inline=False)
        limits = config.get("limits", {})
        if limits:
            lines = []
            for role_id, limit in limits.items():
                limit_role = guild.get_role(int(role_id))
                lines.append(f"{limit_role.mention if limit_role else role_id}: `{limit}`")
            e.add_field(name="Role Limits", value="\n".join(lines[:20]), inline=False)
        else:
            e.add_field(name="Role Limits", value="No role limits set.", inline=False)
        return e

    @commands.group(name="vouch", invoke_without_command=True)
    async def vouch_prefix(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        if ctx.guild is None:
            return
        if member is None:
            await ctx.reply("Use `vouch @member`, `vouch role @role`, `vouch limit @role 5`, or `vouch status`.", mention_author=False)
            return
        result = await self.give_vouch(ctx.guild, ctx.author, member)
        await ctx.reply(result, mention_author=False)

    @vouch_prefix.command(name="role")
    async def vouch_prefix_role(self, ctx: commands.Context, role: discord.Role) -> None:
        if not await self.is_config_owner(ctx.guild, ctx.author):
            await ctx.reply("Only the server owner or OWNER_IDS can set the vouch role.", mention_author=False)
            return
        problem = await self.bot_can_give_role(ctx.guild, role)
        if problem:
            await ctx.reply(problem, mention_author=False)
            return
        config = await self.get_config(ctx.guild.id)
        config["role_id"] = role.id
        await self.save_config(ctx.guild.id, config)
        await ctx.reply(f"Vouch role set to {role.mention}.", mention_author=False)

    @vouch_prefix.command(name="limit")
    async def vouch_prefix_limit(self, ctx: commands.Context, role: discord.Role, limit: int) -> None:
        if not await self.is_config_owner(ctx.guild, ctx.author):
            await ctx.reply("Only the server owner or OWNER_IDS can set vouch limits.", mention_author=False)
            return
        config = await self.get_config(ctx.guild.id)
        config.setdefault("limits", {})[str(role.id)] = max(0, min(limit, 100000))
        await self.save_config(ctx.guild.id, config)
        await ctx.reply(f"{role.mention} can now give `{config['limits'][str(role.id)]}` vouches.", mention_author=False)

    @vouch_prefix.command(name="status")
    async def vouch_prefix_status(self, ctx: commands.Context) -> None:
        config = await self.get_config(ctx.guild.id)
        await ctx.reply(embed=self.status_embed(ctx.guild, config), mention_author=False)

    @vouch_prefix.command(name="reset")
    async def vouch_prefix_reset(self, ctx: commands.Context, member: discord.Member) -> None:
        if not await self.is_config_owner(ctx.guild, ctx.author):
            await ctx.reply("Only the server owner or OWNER_IDS can reset vouches.", mention_author=False)
            return
        config = await self.get_config(ctx.guild.id)
        config.setdefault("given", {}).pop(str(member.id), None)
        await self.save_config(ctx.guild.id, config)
        await ctx.reply(f"Reset vouches used by {member.mention}.", mention_author=False)

    @vouch_group.command(name="give", description="Vouch a member and give the configured vouch role")
    async def vouch_give(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        result = await self.give_vouch(interaction.guild, interaction.user, member)
        await interaction.response.send_message(result)

    @vouch_group.command(name="set_role", description="Server owner: set the role given by vouches")
    async def vouch_set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.is_config_owner(interaction.guild, interaction.user):
            await interaction.response.send_message("Only the server owner or OWNER_IDS can set the vouch role.", ephemeral=True)
            return
        problem = await self.bot_can_give_role(interaction.guild, role)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        config["role_id"] = role.id
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message(f"Vouch role set to {role.mention}.", ephemeral=True)

    @vouch_group.command(name="set_limit", description="Server owner: set how many vouches a role can give")
    async def vouch_set_limit(self, interaction: discord.Interaction, role: discord.Role, limit: app_commands.Range[int, 0, 100000]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.is_config_owner(interaction.guild, interaction.user):
            await interaction.response.send_message("Only the server owner or OWNER_IDS can set vouch limits.", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        config.setdefault("limits", {})[str(role.id)] = int(limit)
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message(f"{role.mention} can now give `{limit}` vouches.", ephemeral=True)

    @vouch_group.command(name="status", description="Show vouch settings")
    async def vouch_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        await interaction.response.send_message(embed=self.status_embed(interaction.guild, config), ephemeral=True)

    @vouch_group.command(name="reset", description="Server owner: reset one member's used vouches")
    async def vouch_reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.is_config_owner(interaction.guild, interaction.user):
            await interaction.response.send_message("Only the server owner or OWNER_IDS can reset vouches.", ephemeral=True)
            return
        config = await self.get_config(interaction.guild_id)
        config.setdefault("given", {}).pop(str(member.id), None)
        await self.save_config(interaction.guild_id, config)
        await interaction.response.send_message(f"Reset vouches used by {member.mention}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Vouch(bot))
