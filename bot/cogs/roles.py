from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


class RoleSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role]) -> None:
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles[:25]]
        super().__init__(placeholder="Choose roles", min_values=0, max_values=max(1, len(options)), options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = {int(v) for v in self.values}
        member = interaction.user
        added = []
        removed = []
        for option in self.options:
            role = interaction.guild.get_role(int(option.value))
            if role is None:
                continue
            if role.id in selected and role not in member.roles:
                await member.add_roles(role, reason="Self-role panel")
                added.append(role.name)
            elif role.id not in selected and role in member.roles:
                await member.remove_roles(role, reason="Self-role panel")
                removed.append(role.name)
        await interaction.response.send_message(f"Added: {', '.join(added) or 'none'}\nRemoved: {', '.join(removed) or 'none'}", ephemeral=True)


class RolePanel(discord.ui.View):
    def __init__(self, roles: list[discord.Role]) -> None:
        super().__init__(timeout=None)
        self.add_item(RoleSelect(roles))


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    roles = app_commands.Group(name="roles", description="Reaction, button, and dropdown roles")

    @roles.command(name="panel", description="Create a dropdown self-role panel")
    @app_admin()
    async def panel(self, interaction: discord.Interaction, title: str, role1: discord.Role, role2: discord.Role | None = None, role3: discord.Role | None = None, role4: discord.Role | None = None, role5: discord.Role | None = None) -> None:
        roles = [r for r in [role1, role2, role3, role4, role5] if r]
        await interaction.channel.send(embed=embed(title, "Pick roles from the menu below."), view=RolePanel(roles))
        await interaction.response.send_message("Role panel posted.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
