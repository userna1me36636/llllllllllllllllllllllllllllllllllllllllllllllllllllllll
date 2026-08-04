from __future__ import annotations

import io
import math

import aiohttp
import discord
import qrcode
from discord import app_commands
from discord.ext import commands

from bot.core.utils import embed, parse_duration, random_code


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.deleted: dict[int, discord.Message] = {}
        self.edited: dict[int, tuple[str, str]] = {}

    utility = app_commands.Group(name="utility", description="Useful server tools")

    @utility.command(name="ping", description="Show bot latency")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong: {round(self.bot.latency * 1000)}ms")

    @utility.command(name="avatar", description="Show a user's avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        await interaction.response.send_message(embed=embed("Avatar", member.display_avatar.url).set_image(url=member.display_avatar.url))

    @utility.command(name="userinfo", description="Show user information")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        member = member or interaction.user
        e = embed("User Info", member.mention)
        e.add_field(name="ID", value=str(member.id))
        e.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at) if member.joined_at else "unknown")
        e.add_field(name="Created", value=discord.utils.format_dt(member.created_at))
        e.add_field(name="Roles", value=str(len(member.roles) - 1))
        await interaction.response.send_message(embed=e)

    @utility.command(name="serverinfo", description="Show server information")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        e = embed("Server Info", g.name)
        e.add_field(name="Members", value=str(g.member_count))
        e.add_field(name="Channels", value=str(len(g.channels)))
        e.add_field(name="Roles", value=str(len(g.roles)))
        e.add_field(name="Owner", value=f"<@{g.owner_id}>")
        await interaction.response.send_message(embed=e)

    @utility.command(name="poll", description="Create a quick poll")
    async def poll(self, interaction: discord.Interaction, question: str, option_a: str, option_b: str, option_c: str | None = None, option_d: str | None = None) -> None:
        options = [o for o in [option_a, option_b, option_c, option_d] if o]
        msg = await interaction.channel.send(embed=embed("Poll", question + "\n" + "\n".join(f"{i+1}. {o}" for i, o in enumerate(options))))
        for emoji in ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][:len(options)]:
            await msg.add_reaction(emoji)
        await interaction.response.send_message("Poll posted.", ephemeral=True)

    @utility.command(name="say", description="Make the bot say a message")
    @app_commands.default_permissions(manage_messages=True)
    async def say(self, interaction: discord.Interaction, message: str) -> None:
        await interaction.channel.send(message)
        await interaction.response.send_message("Sent.", ephemeral=True)

    @utility.command(name="embed", description="Send a simple embed")
    @app_commands.default_permissions(manage_messages=True)
    async def send_embed(self, interaction: discord.Interaction, title: str, description: str) -> None:
        await interaction.channel.send(embed=embed(title, description))
        await interaction.response.send_message("Embed sent.", ephemeral=True)

    @utility.command(name="remind", description="Set a reminder")
    async def remind(self, interaction: discord.Interaction, duration: str, text: str) -> None:
        when = discord.utils.utcnow() + parse_duration(duration)
        await interaction.response.send_message(f"I will remind you {discord.utils.format_dt(when, 'R')}.", ephemeral=True)
        await discord.utils.sleep_until(when)
        await interaction.user.send(f"Reminder: {text}")

    @utility.command(name="qr", description="Generate a QR code")
    async def qr(self, interaction: discord.Interaction, text: str) -> None:
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        buf.seek(0)
        await interaction.response.send_message(file=discord.File(buf, "qr.png"), ephemeral=True)

    @utility.command(name="timestamp", description="Generate a Discord timestamp")
    async def timestamp(self, interaction: discord.Interaction, unix_seconds: int) -> None:
        await interaction.response.send_message(f"<t:{unix_seconds}:F> `<t:{unix_seconds}:F>`", ephemeral=True)

    @utility.command(name="password", description="Generate a strong password")
    async def password(self, interaction: discord.Interaction, length: app_commands.Range[int, 8, 64] = 20) -> None:
        await interaction.response.send_message(random_code(length), ephemeral=True)

    @utility.command(name="weather", description="Get weather when OPENWEATHER_API_KEY is configured")
    async def weather(self, interaction: discord.Interaction, city: str) -> None:
        key = self.bot.settings.openweather_api_key
        if not key:
            await interaction.response.send_message("Weather needs OPENWEATHER_API_KEY in .env.", ephemeral=True)
            return
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.openweathermap.org/data/2.5/weather", params={"q": city, "appid": key, "units": "imperial"}) as resp:
                data = await resp.json()
        await interaction.response.send_message(embed=embed("Weather", f"{data.get('name', city)}: {data['main']['temp']} F, {data['weather'][0]['description']}"))

    @utility.command(name="calculate", description="Calculate a simple expression")
    async def calculate(self, interaction: discord.Interaction, expression: str) -> None:
        allowed = set("0123456789+-*/(). %")
        if not set(expression) <= allowed:
            await interaction.response.send_message("Only basic math characters are allowed.", ephemeral=True)
            return
        value = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt})
        await interaction.response.send_message(f"`{expression}` = `{value}`")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            self.deleted[message.channel.id] = message

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild and not before.author.bot:
            self.edited[before.channel.id] = (before.content, after.content)

    @utility.command(name="snipe", description="Show last deleted message in this channel")
    async def snipe(self, interaction: discord.Interaction) -> None:
        msg = self.deleted.get(interaction.channel_id)
        await interaction.response.send_message(embed=embed("Snipe", f"{msg.author}: {msg.content}" if msg else "Nothing to snipe."))

    @utility.command(name="editsnipe", description="Show last edited message in this channel")
    async def editsnipe(self, interaction: discord.Interaction) -> None:
        data = self.edited.get(interaction.channel_id)
        await interaction.response.send_message(embed=embed("Edit Snipe", f"Before: {data[0]}\nAfter: {data[1]}" if data else "Nothing to snipe."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
