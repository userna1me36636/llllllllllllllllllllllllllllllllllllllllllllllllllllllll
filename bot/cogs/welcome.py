from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    welcome = app_commands.Group(name="welcome", description="Welcome, goodbye, autorole, and verification")

    @welcome.command(name="configure", description="Configure welcome messages")
    @app_admin()
    async def configure(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {user} to {server}!", goodbye_channel: discord.TextChannel | None = None, autorole: discord.Role | None = None) -> None:
        data = {"channel": channel.id, "message": message, "goodbye_channel": goodbye_channel.id if goodbye_channel else None, "autorole": autorole.id if autorole else None}
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", data, self.bot.settings.default_prefix)
        await interaction.response.send_message("Welcome system configured.", ephemeral=True)

    @welcome.command(name="set", description="Set the welcome channel and message")
    @app_admin()
    async def set_welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {user} to {server}!") -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("welcome", {})
        data["channel"] = channel.id
        data["message"] = message
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", data, self.bot.settings.default_prefix)
        await interaction.response.send_message("Welcome message saved.", ephemeral=True)

    @welcome.command(name="leave", description="Set the leave channel and message")
    @app_admin()
    async def set_leave(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "{user} left the server.") -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("welcome", {})
        data["goodbye_channel"] = channel.id
        data["goodbye_message"] = message
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", data, self.bot.settings.default_prefix)
        await interaction.response.send_message("Leave message saved.", ephemeral=True)

    @welcome.command(name="off", description="Turn off welcome and leave messages")
    @app_admin()
    async def off(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "welcome", {}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Welcome and leave messages turned off.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        cfg = settings.get("welcome", {})
        if cfg.get("autorole"):
            role = member.guild.get_role(cfg["autorole"])
            if role:
                await member.add_roles(role, reason="Autorole")
        channel = member.guild.get_channel(cfg.get("channel", 0))
        if isinstance(channel, discord.TextChannel):
            text = cfg.get("message", "Welcome {user} to {server}!").format(user=member.mention, server=member.guild.name)
            await channel.send(embed=embed("Welcome", text))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        cfg = settings.get("welcome", {})
        channel = member.guild.get_channel(cfg.get("goodbye_channel", 0))
        if isinstance(channel, discord.TextChannel):
            text = cfg.get("goodbye_message", "{user} left the server.").format(user=str(member), server=member.guild.name)
            await channel.send(embed=embed("Goodbye", text))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
