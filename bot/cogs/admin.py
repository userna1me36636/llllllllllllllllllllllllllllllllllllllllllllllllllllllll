from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner, has_guild_permissions


def clean_embed(title: str, description: str | None = None) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.from_rgb(170, 22, 38))


def prefix_command_names(bot: commands.Bot) -> list[str]:
    names: list[str] = []
    for command in bot.walk_commands():
        if command.hidden or command.name.startswith("_"):
            continue
        name = command.qualified_name
        if name not in names:
            names.append(name)
    return sorted(names)


class PrefixModal(discord.ui.Modal):
    def __init__(self, cog: "Admin", command_name: str, query: str = "", page: int = 0) -> None:
        super().__init__(title=f"Set Prefix: {command_name}")
        self.cog = cog
        self.command_name = command_name
        self.query = query
        self.page = page
        self.prefix = discord.ui.TextInput(label="Prefix", placeholder="Example: ,, !, ?, .", min_length=1, max_length=12)
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        overrides[self.command_name] = [str(self.prefix).strip()[:12]]
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", overrides, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query, self.page), view=PrefixPanel(self.cog, self.query, self.page))


class PrefixSearchModal(discord.ui.Modal):
    def __init__(self, cog: "Admin") -> None:
        super().__init__(title="Search Commands")
        self.cog = cog
        self.query = discord.ui.TextInput(label="Search", placeholder="Example: vc, music, theme, drag", required=False, max_length=40)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = str(self.query).strip()
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, query), view=PrefixPanel(self.cog, query))


class PrefixSetAllModal(discord.ui.Modal):
    def __init__(self, cog: "Admin", query: str = "", page: int = 0) -> None:
        super().__init__(title="Set All Prefixes")
        self.cog = cog
        self.query = query
        self.page = page
        self.prefix = discord.ui.TextInput(label="Prefix for every prefix command", placeholder="Example: ,", min_length=1, max_length=12)
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = str(self.prefix).strip()[:12]
        overrides = {name: [value] for name in prefix_command_names(self.cog.bot)}
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", overrides, self.cog.bot.settings.default_prefix)
        await self.cog.bot.db.set_prefix(interaction.guild_id, value, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query, self.page), view=PrefixPanel(self.cog, self.query, self.page))


class PrefixCommandSelect(discord.ui.Select):
    def __init__(self, cog: "Admin", query: str = "", page: int = 0) -> None:
        self.cog = cog
        self.query = query
        self.page = max(0, page)
        all_names = prefix_command_names(cog.bot)
        filtered = [name for name in all_names if query.lower() in name.lower()] if query else all_names
        page_names = filtered[self.page * 25:self.page * 25 + 25]
        options = [
            discord.SelectOption(label=name[:100], value=name, description=f"Current command: {name}"[:100])
            for name in page_names
        ] or [discord.SelectOption(label="No commands found", value="__none__", description="Try search")]
        super().__init__(placeholder=f"Pick a command - page {self.page + 1}", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.values[0] == "__none__":
            await interaction.response.send_message(embed=clean_embed("No Command Found"), ephemeral=True)
            return
        await interaction.response.send_modal(PrefixModal(self.cog, self.values[0], self.query, self.page))


class PrefixPanel(discord.ui.View):
    def __init__(self, cog: "Admin", query: str = "", page: int = 0) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.query = query
        self.page = max(0, page)
        self.add_item(PrefixCommandSelect(cog, query, self.page))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        allowed = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or await configured_owner(interaction.client, interaction.user)
        if not allowed:
            await interaction.response.send_message(embed=clean_embed("Missing Permission"), ephemeral=True)
        return allowed

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PrefixSearchModal(self.cog))

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query, page), view=PrefixPanel(self.cog, self.query, page))

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        filtered = self.cog.filtered_commands(self.query)
        max_page = max(0, (len(filtered) - 1) // 25)
        page = min(max_page, self.page + 1)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query, page), view=PrefixPanel(self.cog, self.query, page))

    @discord.ui.button(label="Set All", style=discord.ButtonStyle.success)
    async def set_all(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(PrefixSetAllModal(self.cog, self.query, self.page))

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", {}, self.cog.bot.settings.default_prefix)
        await self.cog.bot.db.set_prefix(interaction.guild_id, self.cog.bot.settings.default_prefix, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id, self.query, self.page), view=PrefixPanel(self.cog, self.query, self.page))


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    prefix = app_commands.Group(name="prefix", description="Manage comma prefix commands")

    def filtered_commands(self, query: str = "") -> list[str]:
        all_names = prefix_command_names(self.bot)
        return [name for name in all_names if query.lower() in name.lower()] if query else all_names

    async def prefix_panel_embed(self, guild_id: int, query: str = "", page: int = 0) -> discord.Embed:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        default_prefix = settings.get("prefix", self.bot.settings.default_prefix)
        filtered = self.filtered_commands(query)
        max_page = max(0, (len(filtered) - 1) // 25)
        page = max(0, min(page, max_page))
        page_names = filtered[page * 25:page * 25 + 25]
        e = clean_embed("Prefix Panel", "Pick a command, search, or set every prefix command at once.")
        e.add_field(name="Default Prefix", value=f"`{default_prefix}`", inline=True)
        e.add_field(name="Commands", value=f"`{len(filtered)}`", inline=True)
        e.add_field(name="Page", value=f"`{page + 1}/{max_page + 1}`", inline=True)
        lines = []
        for name in page_names:
            current = overrides.get(name) or overrides.get(name.split()[-1]) or [default_prefix]
            lines.append(f"`{current[0]}{name}`")
        e.add_field(name="Showing", value="\n".join(lines)[:1024] or "No commands found.", inline=False)
        return e

    @commands.group(name="prefix", invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    async def prefix_command(self, ctx: commands.Context, new_prefix: str | None = None) -> None:
        if ctx.guild is None:
            return
        if new_prefix is None:
            settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
            await ctx.reply(embed=clean_embed(f"Prefix: {settings['prefix']}"), mention_author=False)
            return
        await self.bot.db.set_prefix(ctx.guild.id, new_prefix[:12], self.bot.settings.default_prefix)
        await ctx.reply(embed=clean_embed("Prefix Updated"), mention_author=False)

    @prefix_command.command(name="panel")
    @has_guild_permissions(manage_guild=True)
    async def prefix_panel_command(self, ctx: commands.Context) -> None:
        await ctx.reply(embed=await self.prefix_panel_embed(ctx.guild.id), view=PrefixPanel(self), mention_author=False)

    @prefix.command(name="set", description="Set the prefix for this server")
    @app_admin()
    async def slash_prefix_set(self, interaction: discord.Interaction, prefix: str) -> None:
        await self.bot.db.set_prefix(interaction.guild_id, prefix[:12], self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=clean_embed("Prefix Updated"), ephemeral=True)

    @prefix.command(name="panel", description="Open the clickable prefix panel")
    @app_admin()
    async def slash_prefix_panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=await self.prefix_panel_embed(interaction.guild_id), view=PrefixPanel(self), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
