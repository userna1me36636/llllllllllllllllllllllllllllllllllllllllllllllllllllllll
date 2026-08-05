from __future__ import annotations

import datetime as dt
import json
import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed, progress_bar, style_embed


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

    async def theme(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("theme", {})

    async def shop_items(self, guild_id: int) -> dict[str, dict]:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        items = {
            name: {"price": price, "description": "Default shop item.", "role_id": 0}
            for name, price in SHOP.items()
        }
        for name, data in settings.get("economy_shop", {}).items():
            if isinstance(data, dict):
                items[name.lower()] = {
                    "price": int(data.get("price", 0) or 0),
                    "description": str(data.get("description", "Custom shop item."))[:300],
                    "role_id": int(data.get("role_id", 0) or 0),
                }
        return items

    async def economy_embed(self, guild_id: int, title: str, description: str) -> discord.Embed:
        theme = await self.theme(guild_id)
        color = discord.Color(int(theme.get("color", 11146790)))
        return style_embed(embed(title, description, color), banner_url=theme.get("banner_url"), flashy=theme.get("effects", True))

    @economy.command(name="balance", description="Show balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        await interaction.response.defer()
        member = member or interaction.user
        row = await self.account(interaction.guild_id, member.id)
        total = int(row["wallet"]) + int(row["bank"])
        e = await self.economy_embed(interaction.guild_id, "Balance", f"{member.mention}\nWallet: `{row['wallet']}`\nBank: `{row['bank']}`")
        e.add_field(name="Total", value=f"`{total}` coins", inline=True)
        e.add_field(name="Coin Glow", value=progress_bar(min(total, 10000), 10000), inline=True)
        await interaction.followup.send(embed=e)

    @economy.command(name="daily", description="Claim daily coins")
    async def daily(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        row = await self.account(interaction.guild_id, interaction.user.id)
        today = dt.date.today().isoformat()
        if row["last_daily"] == today:
            await interaction.followup.send("Daily already claimed.", ephemeral=True)
            return
        amount = random.randint(150, 300)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+?, last_daily=? WHERE guild_id=? AND user_id=?", amount, today, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(f"You claimed {amount} coins.", ephemeral=True)

    @economy.command(name="weekly", description="Claim weekly coins")
    async def weekly(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        row = await self.account(interaction.guild_id, interaction.user.id)
        week = f"{dt.date.today().isocalendar().year}-{dt.date.today().isocalendar().week}"
        if row["last_weekly"] == week:
            await interaction.followup.send("Weekly already claimed.", ephemeral=True)
            return
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+1000, last_weekly=? WHERE guild_id=? AND user_id=?", week, interaction.guild_id, interaction.user.id)
        await interaction.followup.send("You claimed 1000 coins.", ephemeral=True)

    @economy.command(name="work", description="Do a job for coins")
    async def work(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        amount = random.randint(40, 160)
        await self.account(interaction.guild_id, interaction.user.id)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(f"You worked and earned {amount} coins.")

    @economy.command(name="deposit", description="Deposit coins")
    async def deposit(self, interaction: discord.Interaction, amount: int) -> None:
        await interaction.response.defer(ephemeral=True)
        row = await self.account(interaction.guild_id, interaction.user.id)
        amount = min(max(0, amount), row["wallet"])
        await self.bot.db.execute("UPDATE economy SET wallet=wallet-?, bank=bank+? WHERE guild_id=? AND user_id=?", amount, amount, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(f"Deposited {amount}.", ephemeral=True)

    @economy.command(name="withdraw", description="Withdraw coins")
    async def withdraw(self, interaction: discord.Interaction, amount: int) -> None:
        await interaction.response.defer(ephemeral=True)
        row = await self.account(interaction.guild_id, interaction.user.id)
        amount = min(max(0, amount), row["bank"])
        await self.bot.db.execute("UPDATE economy SET bank=bank-?, wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, amount, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(f"Withdrew {amount}.", ephemeral=True)

    @economy.command(name="shop", description="Show shop")
    async def shop(self, interaction: discord.Interaction) -> None:
        items = await self.shop_items(interaction.guild_id)
        lines = []
        for name, data in items.items():
            reward = f" - <@&{data['role_id']}>" if data.get("role_id") else ""
            lines.append(f"`{name}` - `{data['price']}` coins{reward}\n{data.get('description', '')[:120]}")
        e = await self.economy_embed(interaction.guild_id, "Shop", "\n\n".join(lines)[:4000] or "No shop items set.")
        e.add_field(name="Tip", value="Use `/economy buy` to grab an item.", inline=False)
        await interaction.response.send_message(embed=e)

    @economy.command(name="buy", description="Buy a shop item")
    async def buy(self, interaction: discord.Interaction, item: str) -> None:
        await interaction.response.defer(ephemeral=True)
        item = item.lower()
        items = await self.shop_items(interaction.guild_id)
        data = items.get(item)
        if data is None:
            await interaction.followup.send("Item not found.", ephemeral=True)
            return
        price = int(data.get("price", 0) or 0)
        row = await self.account(interaction.guild_id, interaction.user.id)
        if row["wallet"] < price:
            await interaction.followup.send("Not enough coins.", ephemeral=True)
            return
        inv = json.loads(row["inventory"])
        inv.append(item)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet-?, inventory=? WHERE guild_id=? AND user_id=?", price, json.dumps(inv), interaction.guild_id, interaction.user.id)
        role_id = int(data.get("role_id", 0) or 0)
        role = interaction.guild.get_role(role_id) if role_id else None
        if role and isinstance(interaction.user, discord.Member):
            try:
                await interaction.user.add_roles(role, reason=f"Economy shop purchase: {item}")
            except discord.HTTPException:
                await interaction.followup.send(f"Bought `{item}`, but I could not give the reward role.", ephemeral=True)
                return
        await interaction.followup.send(f"Bought `{item}`.", ephemeral=True)

    @economy.command(name="give_coins", description="Admin: give wallet coins to a member")
    @app_admin()
    async def give_coins(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 100_000_000]) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.account(interaction.guild_id, member.id)
        await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, interaction.guild_id, member.id)
        row = await self.account(interaction.guild_id, member.id)
        await interaction.followup.send(f"Gave `{amount}` coins to {member.mention}. Wallet: `{row['wallet']}`.", ephemeral=True)

    @economy.command(name="take_coins", description="Admin: remove wallet coins from a member")
    @app_admin()
    async def take_coins(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 1, 100_000_000]) -> None:
        await interaction.response.defer(ephemeral=True)
        row = await self.account(interaction.guild_id, member.id)
        total = max(0, row["wallet"] - amount)
        await self.bot.db.execute("UPDATE economy SET wallet=? WHERE guild_id=? AND user_id=?", total, interaction.guild_id, member.id)
        await interaction.followup.send(f"Removed `{amount}` coins from {member.mention}. Wallet: `{total}`.", ephemeral=True)

    @economy.command(name="set_wallet", description="Admin: set a member's wallet coins")
    @app_admin()
    async def set_wallet(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 0, 100_000_000]) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.account(interaction.guild_id, member.id)
        await self.bot.db.execute("UPDATE economy SET wallet=? WHERE guild_id=? AND user_id=?", amount, interaction.guild_id, member.id)
        await interaction.followup.send(f"Set {member.mention}'s wallet to `{amount}` coins.", ephemeral=True)

    @economy.command(name="set_bank", description="Admin: set a member's bank coins")
    @app_admin()
    async def set_bank(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, 0, 100_000_000]) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.account(interaction.guild_id, member.id)
        await self.bot.db.execute("UPDATE economy SET bank=? WHERE guild_id=? AND user_id=?", amount, interaction.guild_id, member.id)
        await interaction.followup.send(f"Set {member.mention}'s bank to `{amount}` coins.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
