from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


class CompanionBots(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log = logging.getLogger("bot.companions")
        self.clients: list[discord.Client] = []
        self.tasks: list[asyncio.Task] = []

    vcbots = app_commands.Group(name="vcbots", description="Admin companion bots that sit in voice channels")

    async def cog_load(self) -> None:
        tokens = self.bot.settings.companion_bot_tokens[:20]
        for token in tokens:
            intents = discord.Intents.default()
            intents.guilds = True
            intents.voice_states = True
            client = discord.Client(intents=intents)
            self.clients.append(client)
            self.tasks.append(asyncio.create_task(self.start_client(client, token)))

    async def cog_unload(self) -> None:
        for client in self.clients:
            await client.close()
        for task in self.tasks:
            task.cancel()

    async def start_client(self, client: discord.Client, token: str) -> None:
        try:
            await client.start(token)
        except Exception:
            self.log.exception("Companion bot failed to start")

    def client_name(self, index: int, client: discord.Client) -> str:
        user = client.user
        return f"{index}: {user} ({user.id})" if user else f"{index}: starting/not ready"

    async def ready_client(self, index: int) -> discord.Client | None:
        if index < 1 or index > len(self.clients):
            return None
        client = self.clients[index - 1]
        if not client.is_ready():
            return None
        return client

    @vcbots.command(name="list", description="List configured companion bots")
    @app_admin()
    async def list_bots(self, interaction: discord.Interaction) -> None:
        if not self.clients:
            await interaction.response.send_message("No companion bots are configured. Add COMPANION_BOT_TOKENS in Railway.", ephemeral=True)
            return
        e = embed("Companion Bots")
        for index, client in enumerate(self.clients, start=1):
            voice = "not in VC"
            if client.voice_clients:
                vc = client.voice_clients[0]
                voice = f"in <#{vc.channel.id}>"
            e.add_field(name=self.client_name(index, client), value=voice, inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @vcbots.command(name="join", description="Make one companion bot join a voice channel")
    @app_admin()
    async def join(self, interaction: discord.Interaction, bot_number: app_commands.Range[int, 1, 20], channel: discord.VoiceChannel) -> None:
        client = await self.ready_client(bot_number)
        if client is None:
            await interaction.response.send_message("That companion bot is not configured or not ready yet.", ephemeral=True)
            return
        guild = client.get_guild(interaction.guild_id)
        target = guild.get_channel(channel.id) if guild else None
        if not isinstance(target, discord.VoiceChannel):
            await interaction.response.send_message("That companion bot is not in this server. Invite it first.", ephemeral=True)
            return
        existing = discord.utils.get(client.voice_clients, guild=guild)
        if existing:
            await existing.move_to(target)
        else:
            await target.connect(self_deaf=True)
        await interaction.response.send_message(f"Companion bot `{bot_number}` joined {channel.mention}.", ephemeral=True)

    @vcbots.command(name="join_all", description="Make all companion bots join a voice channel")
    @app_admin()
    async def join_all(self, interaction: discord.Interaction, channel: discord.VoiceChannel) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        joined = 0
        for index in range(1, min(20, len(self.clients)) + 1):
            client = await self.ready_client(index)
            if client is None:
                continue
            guild = client.get_guild(interaction.guild_id)
            target = guild.get_channel(channel.id) if guild else None
            if not isinstance(target, discord.VoiceChannel):
                continue
            existing = discord.utils.get(client.voice_clients, guild=guild)
            if existing:
                await existing.move_to(target)
            else:
                await target.connect(self_deaf=True)
            joined += 1
        await interaction.followup.send(f"{joined} companion bot(s) joined {channel.mention}.", ephemeral=True)

    @vcbots.command(name="leave", description="Make one companion bot leave voice")
    @app_admin()
    async def leave(self, interaction: discord.Interaction, bot_number: app_commands.Range[int, 1, 20]) -> None:
        client = await self.ready_client(bot_number)
        if client is None:
            await interaction.response.send_message("That companion bot is not configured or not ready yet.", ephemeral=True)
            return
        guild = client.get_guild(interaction.guild_id)
        existing = discord.utils.get(client.voice_clients, guild=guild)
        if existing:
            await existing.disconnect(force=True)
        await interaction.response.send_message(f"Companion bot `{bot_number}` left voice.", ephemeral=True)

    @vcbots.command(name="leave_all", description="Make all companion bots leave voice")
    @app_admin()
    async def leave_all(self, interaction: discord.Interaction) -> None:
        left = 0
        for client in self.clients:
            guild = client.get_guild(interaction.guild_id) if client.is_ready() else None
            existing = discord.utils.get(client.voice_clients, guild=guild)
            if existing:
                await existing.disconnect(force=True)
                left += 1
        await interaction.response.send_message(f"{left} companion bot(s) left voice.", ephemeral=True)

    @vcbots.command(name="nick", description="Change a companion bot nickname in this server")
    @app_admin()
    async def nick(self, interaction: discord.Interaction, bot_number: app_commands.Range[int, 1, 20], nickname: str) -> None:
        client = await self.ready_client(bot_number)
        if client is None:
            await interaction.response.send_message("That companion bot is not configured or not ready yet.", ephemeral=True)
            return
        guild = client.get_guild(interaction.guild_id)
        member = guild.me if guild else None
        if member is None:
            await interaction.response.send_message("That companion bot is not in this server. Invite it first.", ephemeral=True)
            return
        await member.edit(nick=nickname[:32], reason=f"Companion bot nickname changed by {interaction.user}")
        await interaction.response.send_message(f"Companion bot `{bot_number}` nickname updated.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CompanionBots(bot))
