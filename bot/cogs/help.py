from __future__ import annotations

import discord
from discord.ext import commands
from rapidfuzz import fuzz

from bot.core.utils import embed


class HelpSelect(discord.ui.Select):
    def __init__(self, cog: "Help") -> None:
        self.cog = cog
        options = [discord.SelectOption(label=name, description=f"{len(commands_)} commands") for name, commands_ in cog.catalog.items()]
        super().__init__(placeholder="Choose a category", options=options[:25])

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=self.cog.category_embed(self.values[0]), view=self.view)


class HelpSearch(discord.ui.Modal, title="Search Commands"):
    query = discord.ui.TextInput(label="Command or feature", max_length=80)

    def __init__(self, cog: "Help") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        results: list[tuple[int, str, str]] = []
        for category, names in self.cog.catalog.items():
            for name in names:
                score = fuzz.partial_ratio(str(self.query).lower(), name.lower())
                if score >= 55:
                    results.append((score, category, name))
        results.sort(reverse=True)
        e = embed("Search Results", f"Matches for `{self.query}`")
        for _, category, name in results[:15]:
            e.add_field(name=name, value=category, inline=True)
        if not results:
            e.description = "No matching commands found."
        await interaction.response.send_message(embed=e, ephemeral=True)


class HelpView(discord.ui.View):
    def __init__(self, cog: "Help") -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.add_item(HelpSelect(cog))

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(HelpSearch(self.cog))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.catalog = {
            "Moderation": ["ban", "softban", "tempban", "unban", "kick", "timeout", "untimeout", "mute", "warn", "warnings", "purge", "slowmode", "role", "channel"],
            "Automod": ["automod configure", "automod status", "anti spam", "anti links", "anti invites", "anti caps", "anti profanity"],
            "Security": ["antinuke configure", "antinuke whitelist", "godmode add", "godmode remove"],
            "Community": ["ticket panel", "roles panel", "welcome configure", "level rank", "giveaway start"],
            "Music": ["music play", "pause", "resume", "skip", "queue", "loop", "shuffle", "volume", "lyrics"],
            "Utility": ["avatar", "serverinfo", "userinfo", "poll", "remind", "qr", "timestamp", "weather", "translate", "password"],
            "Economy": ["daily", "weekly", "balance", "deposit", "withdraw", "shop", "buy", "trade"],
            "Configuration": ["prefix", "config panel", "config set"],
        }

    def category_embed(self, category: str) -> discord.Embed:
        e = embed(category, "Commands, permissions, usage, and examples.")
        for name in self.catalog.get(category, []):
            e.add_field(name=f"/{name}", value=f"Prefix: `{{prefix}}{name}`\nPermissions: context aware", inline=False)
        return e

    def overview_embed(self, prefix: str) -> discord.Embed:
        e = embed("Help", f"Current prefix: `{prefix}`\nUse the menu or Search button.")
        for category, names in self.catalog.items():
            e.add_field(name=category, value=", ".join(f"`/{n}`" for n in names[:6]), inline=False)
        return e

    @commands.hybrid_command(name="help")
    async def help_command(self, ctx: commands.Context, *, query: str | None = None) -> None:
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        prefix = self.bot.settings.default_prefix
        if ctx.guild:
            settings = await self.bot.db.get_settings(ctx.guild.id, self.bot.settings.default_prefix)
            prefix = settings["prefix"]
        if query and query.title() in self.catalog:
            await ctx.send(embed=self.category_embed(query.title()), ephemeral=bool(ctx.interaction))
            return
        await ctx.send(embed=self.overview_embed(prefix), view=HelpView(self), ephemeral=bool(ctx.interaction))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
