from __future__ import annotations

import json

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner, has_guild_permissions
from bot.core.utils import embed


def prefix_command_names(bot: commands.Bot) -> list[str]:
    names = []
    for command in bot.walk_commands():
        if command.name.startswith("_"):
            continue
        name = command.qualified_name
        if name not in names:
            names.append(name)
    return sorted(names)


class PrefixModal(discord.ui.Modal):
    def __init__(self, cog: "Admin", command_name: str, query: str = "") -> None:
        super().__init__(title=f"Set Prefix: {command_name}")
        self.cog = cog
        self.command_name = command_name
        self.query = query
        self.prefix = discord.ui.TextInput(label="Prefix", placeholder="Example: !, ?, $, .", min_length=1, max_length=12)
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        value = str(self.prefix).strip()[:12]
        overrides[self.command_name] = [value]
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", overrides, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query), view=PrefixPanel(self.cog, self.query))


class PrefixSearchModal(discord.ui.Modal):
    def __init__(self, cog: "Admin") -> None:
        super().__init__(title="Search Commands")
        self.cog = cog
        self.query = discord.ui.TextInput(label="Search", placeholder="Example: ownerrole, vc, vouch, ban", required=False, max_length=40)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = str(self.query).strip()
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, query), view=PrefixPanel(self.cog, query))


class PrefixSetAllModal(discord.ui.Modal):
    def __init__(self, cog: "Admin", query: str = "") -> None:
        super().__init__(title="Set All Command Prefixes")
        self.cog = cog
        self.query = query
        self.prefix = discord.ui.TextInput(label="Prefix for every command", placeholder="Example: !, ?, $, .", min_length=1, max_length=12)
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        value = str(self.prefix).strip()[:12]
        overrides = {name: [value] for name in prefix_command_names(self.cog.bot)}
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", overrides, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query), view=PrefixPanel(self.cog, self.query))


class PrefixCommandSelect(discord.ui.Select):
    def __init__(self, cog: "Admin", query: str = "") -> None:
        self.cog = cog
        self.query = query
        all_names = prefix_command_names(cog.bot)
        filtered = [name for name in all_names if query.lower() in name.lower()] if query else all_names
        options = [
            discord.SelectOption(label=name[:100], value=name, description=f"Change prefix for {name}"[:100])
            for name in filtered[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No commands found", value="__none__", description="Try another search")]
        super().__init__(placeholder="Pick a command to customize", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "__none__":
            await interaction.response.send_message("No command selected.", ephemeral=True)
            return
        await interaction.response.send_modal(PrefixModal(self.cog, self.values[0], self.query))


class PrefixPanel(discord.ui.View):
    def __init__(self, cog: "Admin", query: str = "") -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.query = query
        self.add_item(PrefixCommandSelect(cog, query))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        allowed = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or await configured_owner(interaction.client, interaction.user)
        if not allowed:
            await interaction.response.send_message("You need Manage Server to use this panel.", ephemeral=True)
        return allowed

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PrefixSearchModal(self.cog))

    @discord.ui.button(label="Set All", style=discord.ButtonStyle.success)
    async def set_all(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PrefixSetAllModal(self.cog, self.query))

    @discord.ui.button(label="Clear Command Prefixes", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", {}, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query), view=PrefixPanel(self.cog, self.query))


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    prefix = app_commands.Group(name="prefix", description="Manage server prefixes")
    config = app_commands.Group(name="config", description="Configure bot modules")

    async def prefix_panel_embed(self, guild_id: int, query: str = "") -> discord.Embed:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        default_prefix = settings.get("prefix", self.bot.settings.default_prefix)
        all_names = prefix_command_names(self.bot)
        filtered = [name for name in all_names if query.lower() in name.lower()] if query else all_names
        e = embed("Prefix Panel", "Search commands, pick one from the menu, or set every command to one prefix.")
        e.add_field(name="Default Prefix", value=f"`{default_prefix}`", inline=True)
        e.add_field(name="Commands", value=f"`{len(all_names)}` total", inline=True)
        e.add_field(name="Search", value=f"`{query or 'All commands'}`", inline=True)
        lines = []
        for name in filtered[:25]:
            prefixes = overrides.get(name) or overrides.get(name.split()[-1]) or [default_prefix]
            lines.append(f"`{prefixes[0]}{name}`")
        e.add_field(
            name="Showing Prefixes",
            value="\n".join(lines)[:1024] or "No commands found.",
            inline=False,
        )
        e.set_footer(text="Only 25 can show at once in Discord's menu. Use Search to find more.")
        return e

    @commands.command(name="prefix")
    @has_guild_permissions(manage_guild=True)
    async def prefix_command(self, ctx: commands.Context, new_prefix: str | None = None) -> None:
        """Show or change this server's prefix."""
        if ctx.guild is None:
            return
        if new_prefix is None:
            settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
            await ctx.reply(f"Current prefix: `{settings['prefix']}`", mention_author=False)
            return
        await self.bot.db.set_prefix(ctx.guild.id, new_prefix[:12], self.bot.settings.default_prefix)
        await ctx.reply(f"Prefix changed to `{new_prefix[:12]}`.", mention_author=False)

    @prefix.command(name="set", description="Set the prefix for this server")
    @app_admin()
    async def slash_prefix_set(self, interaction: discord.Interaction, prefix: str) -> None:
        await self.bot.db.set_prefix(interaction.guild_id, prefix[:12], self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Prefix changed to `{prefix[:12]}`.", ephemeral=True)

    @prefix.command(name="panel", description="Open the clickable prefix panel")
    @app_admin()
    async def slash_prefix_panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=await self.prefix_panel_embed(interaction.guild_id), view=PrefixPanel(self), ephemeral=True)

    @config.command(name="panel", description="Open the configuration overview")
    @app_admin()
    async def config_panel(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = embed("Configuration")
        for key in sorted(k for k in settings if k != "prefix"):
            value = settings[key]
            if isinstance(value, (dict, list)):
                value = json.dumps(value)[:900]
            e.add_field(name=key, value=f"`{value}`", inline=False)
        e.add_field(name="prefix", value=f"`{settings['prefix']}`", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @config.command(name="set", description="Set a simple configuration value")
    @app_admin()
    async def config_set(self, interaction: discord.Interaction, key: str, value: str) -> None:
        if interaction.guild_id is None:
            return
        parsed: object
        lowered = value.lower()
        if lowered in {"true", "false"}:
            parsed = lowered == "true"
        else:
            try:
                parsed = int(value)
            except ValueError:
                parsed = value
        await self.bot.db.set_settings_value(interaction.guild_id, key, parsed, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"`{key}` updated.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
