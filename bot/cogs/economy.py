from __future__ import annotations

import datetime as dt
import json
import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.utils import embed


SHOP = {"cookie": 50, "badge": 500, "vip-pass": 2500}


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    economy = app_commands.Group(name="economy", description="Wallet, bank, shop, jobs, and trading")

    async def account(self, guild_id: int, user_id: int):
        row = await self.bot.db.fetchrow("SELECT * FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        if row is None:
            await self.bot.db.execute("INSERT INTO economy(guild_id,user_id) VALUES(?,?)", guild_id, user_id)
            row = await self.bot.db.fetchrow("SELECT * FROM economy WHERE guild_id=? AND user_id=?", guild_id, user_id)
        return row

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
        await interaction.response.send_message(embed=embed("Shop", "\n".join(f"{k}: {v}" for k, v in SHOP.items())))

    @economy.command(name="buy", description="Buy a shop item")
    async def buy(self, interaction: discord.Interaction, item: str) -> None:
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
        await interaction.response.send_message(f"Bought `{item}`.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
