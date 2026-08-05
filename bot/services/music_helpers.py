from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

import discord

log = logging.getLogger(__name__)


@dataclass
class HelperStatus:
    name: str
    ready: bool
    in_server: bool
    connected_channel: str | None


class MusicHelperManager:
    def __init__(self) -> None:
        raw = os.getenv("MUSIC_HELPER_TOKENS", "")
        tokens = [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
        self.tokens = tokens[:10]
        self.clients: list[discord.Client] = []
        self.tasks: list[asyncio.Task] = []
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        for index, token in enumerate(self.tokens, start=1):
            intents = discord.Intents.default()
            intents.guilds = True
            intents.voice_states = True
            client = discord.Client(intents=intents)
            self.clients.append(client)
            self.tasks.append(asyncio.create_task(self._run_client(client, token, index)))

    async def _run_client(self, client: discord.Client, token: str, index: int) -> None:
        try:
            await client.start(token)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Music helper %s could not start: %s", index, type(exc).__name__)

    async def close(self) -> None:
        for client in self.clients:
            if not client.is_closed():
                await client.close()
        for task in self.tasks:
            if not task.done():
                task.cancel()

    def configured_count(self) -> int:
        return len(self.tokens)

    def ready_clients(self) -> list[discord.Client]:
        return [client for client in self.clients if client.is_ready()]

    async def wait_ready(self, seconds: float = 8.0) -> None:
        if not self.clients:
            return
        deadline = asyncio.get_running_loop().time() + seconds
        while asyncio.get_running_loop().time() < deadline:
            if all(client.is_ready() or client.is_closed() for client in self.clients):
                return
            await asyncio.sleep(0.25)

    def _voice_client_for(self, client: discord.Client, guild_id: int) -> discord.VoiceClient | None:
        for vc in client.voice_clients:
            if vc.guild and vc.guild.id == guild_id:
                return vc
        return None

    async def summon(self, guild_id: int, channel_id: int, count: int) -> tuple[int, list[str]]:
        await self.wait_ready()
        joined = 0
        errors: list[str] = []
        for client in self.ready_clients()[: max(0, min(count, 10))]:
            guild = client.get_guild(guild_id)
            if guild is None:
                errors.append(f"{client.user}: not invited to this server")
                continue
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                errors.append(f"{client.user}: cannot see that voice channel")
                continue
            existing = self._voice_client_for(client, guild_id)
            try:
                if existing and existing.channel and existing.channel.id == channel_id:
                    joined += 1
                elif existing:
                    await existing.move_to(channel)
                    joined += 1
                else:
                    await channel.connect(self_deaf=True)
                    joined += 1
            except discord.ClientException:
                joined += 1
            except Exception as exc:
                errors.append(f"{client.user}: {type(exc).__name__}")
        return joined, errors[:5]

    async def release(self, guild_id: int) -> int:
        left = 0
        for client in self.ready_clients():
            vc = self._voice_client_for(client, guild_id)
            if vc:
                try:
                    await vc.disconnect(force=True)
                    left += 1
                except Exception:
                    pass
        return left

    def status(self, guild_id: int) -> list[HelperStatus]:
        rows: list[HelperStatus] = []
        for client in self.clients:
            name = str(client.user) if client.user else "Starting..."
            guild = client.get_guild(guild_id) if client.is_ready() else None
            vc = self._voice_client_for(client, guild_id)
            channel_name = vc.channel.name if vc and vc.channel else None
            rows.append(HelperStatus(name, client.is_ready(), guild is not None, channel_name))
        return rows
