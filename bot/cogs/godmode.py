from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin


class GodMode(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    godmode = app_commands.Group(name="godmode", description="Manage protected users and roles")

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GodMode(bot))
