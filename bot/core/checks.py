from __future__ import annotations

import discord
from discord.ext import commands


def guild_only():
    return commands.guild_only()


def has_guild_permissions(**perms: bool):
    return commands.has_guild_permissions(**perms)


async def is_owner_or_admin(ctx: commands.Context) -> bool:
    if await ctx.bot.is_owner(ctx.author):
        return True
    return bool(getattr(ctx.author.guild_permissions, "administrator", False))


def owner_or_admin():
    return commands.check(is_owner_or_admin)


def app_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return interaction.user.guild_permissions.administrator or await interaction.client.is_owner(interaction.user)

    return discord.app_commands.check(predicate)
