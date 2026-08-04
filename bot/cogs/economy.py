from __future__ import annotations

import datetime as dt
import json
import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


SHOP = {
    "cookie": 50,
    "badge": 500,
    "vip-pass": 2500,
    "vc-mute-perms": 10_000,
    "god-mode": 50_000,
}


class EconomyPanel(discord.ui.View):
    def __init__(self, cog: "Economy") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Balance", style=discord.ButtonStyle.primary, custom_id="economy:balance")
    async def balance(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        row = await self.cog.account(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            embed=embed("Balance", f"{interaction.user.mention}\nWallet: {row['wallet']}\nBank: {row['bank']}"),
            ephemeral=True,
        )

    @discord.ui.button(label="Daily", style=discord.ButtonStyle.success, custom_id="economy:daily")
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        row = await self.cog.account(interaction.guild_id, interaction.user.id)
        today = dt.date.today().isoformat()
        if row["last_daily"] == today:
            await interaction.response.send_message("Daily already claimed.", ephemeral=True)
            return
        amount = random.randint(150, 300)
        await self.cog.bot.db.execute(
            "UPDATE economy SET wallet=wallet+?, last_daily=? WHERE guild_id=? AND user_id=?",
            amount,
            today,
            interaction.guild_id,
            interaction.user.id,
        )
        await interaction.response.send_message(f"You claimed {amount} coins.", ephemeral=True)

    @discord.ui.button(label="Work", style=discord.ButtonStyle.secondary, custom_id="economy:work")
    async def work(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        amount = random.randint(40, 160)
        await self.cog.account(interaction.guild_id, interaction.user.id)
        await self.cog.bot.db.execute(
            "UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?",
            amount,
            interaction.guild_id,
            interaction.user.id,
        )
        await interaction.response.send_message(f"You worked and earned {amount} coins.", ephemeral=True)

    @discord.ui.button(label="Shop", style=discord.ButtonStyle.secondary, custom_id="economy:shop")
    async def shop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(embed=self.cog.shop_embed(), ephemeral=True)


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.add_view(EconomyPanel(self))

    economy = app_commands.Group(name="economy", description="Wallet, bank, shop, jobs, and trading")

    def shop_embed(self) -> discord.Embed:
        return embed("Shop", "\n".join(f"`{k}`: {v} coins" for k, v in SHOP.items()))

    def panel_embed(self) -> discord.Embed:
        e = embed(
            "Economy Game",
            "Earn coins, save them in your bank, and buy perks from the shop.",
        )
        e.add_field(name="Earn", value="`/economy daily`\n`/economy weekly`\n`/economy work`", inline=True)
        e.add_field(name="Money", value="`/economy balance`\n`/economy deposit`\n`/economy withdraw`", inline=True)
        e.add_field(name="Shop", value="`/economy shop`\n`/economy buy item: vc-mute-perms`\n`/economy buy item: god-mode`", inline=False)
        e.add_field(name="Premium Items", value="`vc-mute-perms` - 10000 coins\n`god-mode` - 50000 coins", inline=False)
        e.set_footer(text="Use the buttons below for quick actions.")
        return e

    async def account(self, guild_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT * FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        if row is None:
            await self.bot.db.execute("INSERT INTO economy(guild_id,user_id) VALUES(?,?)", guild_id, user_id)
            row = await self.bot.db.fetchrow("SELECT * FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        return row

    async def notify_purchase(self, guild: discord.Guild, buyer: discord.Member, item: str, price: int) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        channel = guild.get_channel(settings.get("economy_notify_channel", 0))
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed("Economy Purchase", f"{buyer.mention} bought `{item}` for `{price}` coins."))

    async def give_vc_mute_perms(self, member: discord.Member) -> discord.Role:
        role = discord.utils.get(member.guild.roles, name="Economy VC Mute")
        if role is None:
            permissions = discord.Permissions.none()
            permissions.mute_members = True
            role = await member.guild.create_role(
                name="Economy VC Mute",
                permissions=permissions,
                reason="Economy purchase role",
            )
        if role not in member.roles:
            await member.add_roles(role, reason="Economy purchase: vc-mute-perms")
        return role

    async def give_god_mode(self, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        data = settings.get("godmode", {"users": [], "roles": []})
        users = data.setdefault("users", [])
        if member.id not in users:
            users.append(member.id)
        await self.bot.db.set_settings_value(member.guild.id, "godmode", data, self.bot.settings.default_prefix)

    @economy.command(name="balance", description="Show balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        row = await self.account(interaction.guild_id, member.id)
        await interaction.response.send_message(embed=embed("Balance", f"{member.mention}\nWallet: {row['wallet']}\nBank: {row['bank']}"))

    @economy.command(name="daily", description="Claim daily coins")
    async def daily(self, interaction: discord.Interaction) -> None:
        row = await self.account(interaction.guild_id, interaction.user.id)
        today = dt.date.today().isoformat()
        if row["last_daily"] == today:
            await interaction.response.send_message("Daily already claimed.", ephemeral=True)
            return
        amount = random.randint(150, 300)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+?, last_daily=? WHERE guild_id=? AND user_id=?", amount, today, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"You claimed {amount} coins.", ephemeral=True)

    @economy.command(name="weekly", description="Claim weekly coins")
    async def weekly(self, interaction: discord.Interaction) -> None:
        row = await self.account(interaction.guild_id, interaction.user.id)
        week = f"{dt.date.today().isocalendar().year}-{dt.date.today().isocalendar().week}"
        if row["last_weekly"] == week:
            await interaction.response.send_message("Weekly already claimed.", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+1000, last_weekly=? WHERE guild_id=? AND user_id=?", week, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message("You claimed 1000 coins.", ephemeral=True)

    @economy.command(name="work", description="Do a job for coins")
    async def work(self, interaction: discord.Interaction) -> None:
        amount = random.randint(40, 160)
        await self.account(interaction.guild_id, interaction.user.id)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"You worked and earned {amount} coins.")

    @economy.command(name="deposit", description="Deposit coins")
    async def deposit(self, interaction: discord.Interaction, amount: int) -> None:
        row = await self.account(interaction.guild_id, interaction.user.id)
        amount = min(max(0, amount), row["wallet"])
        await self.bot.db.execute("UPDATE economy SET wallet=wallet-?, bank=bank+? WHERE guild_id=? AND user_id=?", amount, amount, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"Deposited {amount}.", ephemeral=True)

    @economy.command(name="withdraw", description="Withdraw coins")
    async def withdraw(self, interaction: discord.Interaction, amount: int) -> None:
        row = await self.account(interaction.guild_id, interaction.user.id)
        amount = min(max(0, amount), row["bank"])
        await self.bot.db.execute("UPDATE economy SET bank=bank-?, wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, amount, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(f"Withdrew {amount}.", ephemeral=True)

    @economy.command(name="shop", description="Show shop")
    async def shop(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=self.shop_embed())

    @economy.command(name="panel", description="Post the economy game interface in a channel")
    @app_admin()
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        await target.send(embed=self.panel_embed(), view=EconomyPanel(self))
        await interaction.response.send_message(f"Economy panel posted in {target.mention}.", ephemeral=True)

    @economy.command(name="notify_channel", description="Set the channel for economy purchase alerts")
    @app_admin()
    async def notify_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "economy_notify_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Economy purchase alerts will go to {channel.mention}.", ephemeral=True)

    @economy.command(name="buy", description="Buy a shop item")
    async def buy(self, interaction: discord.Interaction, item: str) -> None:
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        item = item.lower()
        if item not in SHOP:
            await interaction.response.send_message("Item not found.", ephemeral=True)
            return
        row = await self.account(interaction.guild_id, interaction.user.id)
        if row["wallet"] < SHOP[item]:
            await interaction.response.send_message("Not enough coins.", ephemeral=True)
            return
        inv = json.loads(row["inventory"])
        inv.append(item)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet-?, inventory=? WHERE guild_id=? AND user_id=?", SHOP[item], json.dumps(inv), interaction.guild_id, interaction.user.id)
        if item == "vc-mute-perms":
            role = await self.give_vc_mute_perms(interaction.user)
            await interaction.response.send_message(f"Bought `{item}` and received {role.mention}.", ephemeral=True)
        elif item == "god-mode":
            await self.give_god_mode(interaction.user)
            await interaction.response.send_message("Bought `god-mode`. You are now protected by God Mode.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Bought `{item}`.", ephemeral=True)
        await self.notify_purchase(interaction.guild, interaction.user, item, SHOP[item])

    @buy.autocomplete("item")
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=f"{name} - {price} coins", value=name)
            for name, price in SHOP.items()
            if current.lower() in name.lower()
        ][:25]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
