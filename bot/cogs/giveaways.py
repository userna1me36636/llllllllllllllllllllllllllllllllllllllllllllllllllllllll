from __future__ import annotations

import json
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin
from bot.core.utils import embed, parse_duration


class GiveawayView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success, custom_id="giveaway:enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        row = await interaction.client.db.fetchrow("SELECT id, entries FROM giveaways WHERE message_id=? AND ended=0", interaction.message.id)
        if row is None:
            await interaction.response.send_message("This giveaway is closed.", ephemeral=True)
            return
        entries = set(json.loads(row["entries"]))
        entries.add(interaction.user.id)
        await interaction.client.db.execute("UPDATE giveaways SET entries=? WHERE id=?", json.dumps(list(entries)), row["id"])
        await interaction.response.send_message("You are entered.", ephemeral=True)


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.number_giveaways: dict[int, dict[str, int | str]] = {}
        bot.add_view(GiveawayView())
        self.check_giveaways.start()

    giveaway = app_commands.Group(name="giveaway", description="Timed giveaways")
    number = app_commands.Group(name="number", description="Number guessing giveaways")

    def cog_unload(self) -> None:
        self.check_giveaways.cancel()

    @giveaway.command(name="start", description="Start a giveaway")
    @app_admin()
    async def start(self, interaction: discord.Interaction, duration: str, winners: app_commands.Range[int, 1, 20], prize: str) -> None:
        ends = time.time() + parse_duration(duration).total_seconds()
        giveaway_id = await self.bot.db.execute("INSERT INTO giveaways(guild_id,channel_id,prize,winners,ends_at,host_id) VALUES(?,?,?,?,?,?)", interaction.guild_id, interaction.channel_id, prize, winners, ends, interaction.user.id)
        msg = await interaction.channel.send(embed=embed("Giveaway", f"Prize: **{prize}**\nWinners: {winners}\nEnds: <t:{int(ends)}:R>"), view=GiveawayView())
        await self.bot.db.execute("UPDATE giveaways SET message_id=? WHERE id=?", msg.id, giveaway_id)
        await interaction.response.send_message("Giveaway started.", ephemeral=True)

    @giveaway.command(name="reroll", description="Reroll a giveaway")
    @app_admin()
    async def reroll(self, interaction: discord.Interaction, message_id: str) -> None:
        row = await self.bot.db.fetchrow("SELECT prize,winners,entries FROM giveaways WHERE message_id=?", int(message_id))
        if row is None:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True)
            return
        entries = json.loads(row["entries"])
        winners = random.sample(entries, k=min(row["winners"], len(entries))) if entries else []
        await interaction.response.send_message(embed=embed("Reroll", f"{row['prize']}\nWinners: {', '.join(f'<@{w}>' for w in winners) or 'none'}"))

    @giveaway.command(name="end", description="End a giveaway early")
    @app_admin()
    async def end(self, interaction: discord.Interaction, message_id: str) -> None:
        await self.bot.db.execute("UPDATE giveaways SET ends_at=? WHERE message_id=? AND ended=0", time.time(), int(message_id))
        await interaction.response.send_message("Giveaway ending now.", ephemeral=True)

    @number.command(name="gw", description="Start a first-to-guess-the-number giveaway")
    @app_admin()
    async def number_gw(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        number: app_commands.Range[int, 1, 100],
        prize: str = "Number Giveaway",
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command only works in a server.", ephemeral=True)
            return
        if interaction.guild.id in self.number_giveaways:
            active = self.number_giveaways[interaction.guild.id]
            await interaction.response.send_message(
                f"A number giveaway is already active in <#{active['channel_id']}>.",
                ephemeral=True,
            )
            return
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.view_channel and permissions.send_messages and permissions.read_message_history):
            await interaction.response.send_message(
                "I need View Channel, Send Messages, and Read Message History permissions in that channel.",
                ephemeral=True,
            )
            return
        self.number_giveaways[interaction.guild.id] = {
            "channel_id": channel.id,
            "number": int(number),
            "host_id": interaction.user.id,
            "prize": prize[:200],
        }
        await channel.send(
            embed=embed(
                "Number Giveaway",
                f"**Prize:** {prize[:200]}\nGuess a number from **1–100**!\n"
                "The first person to type the correct number wins.",
            )
        )
        await interaction.response.send_message(
            f"Number giveaway started in {channel.mention}. The winning number is **{number}**.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        active = self.number_giveaways.get(message.guild.id)
        if active is None or message.channel.id != active["channel_id"]:
            return
        guess = message.content.strip()
        if not guess.isdecimal() or int(guess) != active["number"]:
            return
        # Remove it before sending so two nearly simultaneous correct guesses cannot both win.
        self.number_giveaways.pop(message.guild.id, None)
        await message.channel.send(
            embed=embed(
                "Number Giveaway Winner!",
                f"Congratulations {message.author.mention}!\n"
                f"You guessed **{active['number']}** first and won **{active['prize']}**.",
            )
        )

    @tasks.loop(seconds=30)
    async def check_giveaways(self) -> None:
        rows = await self.bot.db.fetchall("SELECT * FROM giveaways WHERE ended=0 AND ends_at<=?", time.time())
        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            entries = json.loads(row["entries"])
            winners = random.sample(entries, k=min(row["winners"], len(entries))) if entries else []
            if channel:
                await channel.send(embed=embed("Giveaway Ended", f"{row['prize']}\nWinners: {', '.join(f'<@{w}>' for w in winners) or 'none'}"))
            await self.bot.db.execute("UPDATE giveaways SET ended=1 WHERE id=?", row["id"])

    @check_giveaways.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
