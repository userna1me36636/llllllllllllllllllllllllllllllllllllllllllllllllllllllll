from __future__ import annotations

import json

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed


def prefix_command_names(bot: commands.Bot) -> list[str]:
    names = []
    for command in bot.walk_commands():
        if command.hidden or command.parent is not None:
            continue
        if command.name not in names:
            names.append(command.name)
    priority = ["join", "musicpanel", "wizzpro", "godmode", "prefix", "help"]
    return [name for name in priority if name in names] + sorted(name for name in names if name not in priority)


class PrefixModal(discord.ui.Modal):
    def __init__(self, cog: "Admin", command_name: str) -> None:
        super().__init__(title=f"Set Prefix: {command_name}")
        self.cog = cog
        self.command_name = command_name
        self.prefix = discord.ui.TextInput(label="Prefix", placeholder="Example: !, ?, $, .", min_length=1, max_length=12)
        self.add_item(self.prefix)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        value = str(self.prefix).strip()[:12]
        overrides[self.command_name] = [value]
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", overrides, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id), view=PrefixPanel(self.cog))


class PrefixCommandSelect(discord.ui.Select):
    def __init__(self, cog: "Admin") -> None:
        self.cog = cog
        options = [
            discord.SelectOption(label=name, value=name, description=f"Change prefix for {name}")
            for name in prefix_command_names(cog.bot)[:25]
        ]
        super().__init__(placeholder="Pick a command to customize", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PrefixModal(self.cog, self.values[0]))


class PrefixPanel(discord.ui.View):
    def __init__(self, cog: "Admin") -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(PrefixCommandSelect(cog))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return False
        allowed = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator or await interaction.client.is_owner(interaction.user)
        if not allowed:
            await interaction.response.send_message("You need Manage Server to use this panel.", ephemeral=True)
        return allowed

    @discord.ui.button(label="Clear Command Prefixes", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "command_prefix_overrides", {}, self.cog.bot.settings.default_prefix)
        await interaction.response.edit_message(embed=await self.cog.prefix_panel_embed(interaction.guild_id), view=PrefixPanel(self.cog))


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    prefix = app_commands.Group(name="prefix", description="Manage server prefixes")
    config = app_commands.Group(name="config", description="Configure bot modules")

    async def prefix_panel_embed(self, guild_id: int) -> discord.Embed:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        overrides = settings.get("command_prefix_overrides", {})
        e = embed("Prefix Panel", "Pick a command from the menu, then type the prefix you want for it.")
        e.add_field(name="Default Prefix", value=f"`{settings.get('prefix', self.bot.settings.default_prefix)}`", inline=True)
        e.add_field(name="Custom Command Prefixes", value=str(len(overrides)), inline=True)
        lines = [f"`{prefixes[0]}{name}` for `{name}`" for name, prefixes in sorted(overrides.items()) if prefixes]
        e.add_field(
            name="Current Custom Prefixes",
            value="\n".join(lines[:20]) or "No custom command prefixes yet.",
            inline=False,
        )
        e.set_footer(text="Discord only opens the side command picker for slash commands. Prefix commands work by typing them in chat.")
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

    @commands.command(name="wizzpro", aliases=["wizzpeo", "wizpro", "willpro"])
    @has_guild_permissions(administrator=True)
    async def wizzpro(self, ctx: commands.Context) -> None:
        """Emergency toggle that removes/restores Administrator and Ban Members from roles."""
        if ctx.guild is None or ctx.guild.me is None:
            return
        settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
        state = settings.get("wizzpro", {"active": False, "roles": {}})
        if state.get("active"):
            restored = 0
            for role_id, permissions_value in state.get("roles", {}).items():
                role = ctx.guild.get_role(int(role_id))
                if role is None or role.managed or role >= ctx.guild.me.top_role:
                    continue
                try:
                    await role.edit(permissions=discord.Permissions(int(permissions_value)), reason=f"WizzPro restored by {ctx.author}")
                    restored += 1
                except discord.HTTPException:
                    continue
            await self.bot.db.set_settings_value(ctx.guild.id, "wizzpro", {"active": False, "roles": {}}, self.bot.settings.default_prefix)
            await ctx.reply(f"WizzPro disabled. Restored {restored} role(s).", mention_author=False)
            return

        snapshots: dict[str, int] = {}
        changed = 0
        for role in ctx.guild.roles:
            if role == ctx.guild.default_role or role.managed or role >= ctx.guild.me.top_role:
                continue
            perms = role.permissions
            if not perms.administrator and not perms.ban_members:
                continue
            snapshots[str(role.id)] = perms.value
            perms.administrator = False
            perms.ban_members = False
            try:
                await role.edit(permissions=perms, reason=f"WizzPro enabled by {ctx.author}")
                changed += 1
            except discord.HTTPException:
                continue
        await self.bot.db.set_settings_value(ctx.guild.id, "wizzpro", {"active": True, "roles": snapshots}, self.bot.settings.default_prefix)
        await ctx.reply(
            f"WizzPro enabled. Removed Administrator/Ban Members from {changed} role(s). Run the command again to restore them.",
            mention_author=False,
        )

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
