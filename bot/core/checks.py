from __future__ import annotations

import discord
from discord.ext import commands


async def configured_owner(bot: commands.Bot, user: discord.abc.User | None) -> bool:
    if user is None:
        return False
    settings = getattr(bot, "settings", None)
    if user.id in getattr(settings, "owner_ids", set()):
        return True
    return await bot.is_owner(user)


def guild_only():
    return commands.guild_only()


def has_guild_permissions(**perms: bool):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False
        if await configured_owner(ctx.bot, ctx.author):
            return True
        permissions = ctx.author.guild_permissions
        missing = [name for name, value in perms.items() if getattr(permissions, name, None) != value]
        if missing:
            raise commands.MissingPermissions(missing)
        return True

    return commands.check(predicate)


def app_has_guild_permissions(**perms: bool):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        if await configured_owner(interaction.client, interaction.user):
            return True
        permissions = interaction.user.guild_permissions
        return all(getattr(permissions, name, None) == value for name, value in perms.items())

    return discord.app_commands.check(predicate)


async def is_owner_or_admin(ctx: commands.Context) -> bool:
    if await configured_owner(ctx.bot, ctx.author):
        return True
    return bool(getattr(ctx.author.guild_permissions, "administrator", False))


def owner_or_admin():
    return commands.check(is_owner_or_admin)


def app_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        return interaction.user.guild_permissions.administrator or await configured_owner(interaction.client, interaction.user)

    return discord.app_commands.check(predicate)
