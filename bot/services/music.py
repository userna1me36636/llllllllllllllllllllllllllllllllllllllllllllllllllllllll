from __future__ import annotations

import asyncio
from dataclasses import dataclass

import discord
import yt_dlp


YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": False,
    "default_search": "ytsearch",
    "extract_flat": False,
}
FFMPEG_OPTS = {"options": "-vn"}


@dataclass
class Track:
    title: str
    url: str
    webpage_url: str
    requester_id: int
    duration: int | None = None


class GuildPlayer:
    def __init__(self, guild: discord.Guild) -> None:
        self.guild = guild
        self.queue: asyncio.Queue[Track] = asyncio.Queue()
        self.current: Track | None = None
        self.previous: Track | None = None
        self.history: list[Track] = []
        self.loop_one = False
        self.loop_queue = False
        self.volume = 0.6
        self.panel_channel_id: int | None = None
        self.panel_message_id: int | None = None

    async def resolve(self, query: str, requester_id: int) -> list[Track]:
        def run() -> dict:
            with yt_dlp.YoutubeDL(YTDL_OPTS) as ytdl:
                return ytdl.extract_info(query, download=False)

        data = await asyncio.to_thread(run)
        entries = data.get("entries") or [data]
        tracks = []
        for item in entries:
            if not item:
                continue
            tracks.append(Track(item.get("title", "Unknown track"), item["url"], item.get("webpage_url", query), requester_id, item.get("duration")))
        return tracks

    def source(self, track: Track) -> discord.PCMVolumeTransformer:
        audio = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTS)
        return discord.PCMVolumeTransformer(audio, volume=self.volume)


class MusicManager:
    def __init__(self) -> None:
        self.players: dict[int, GuildPlayer] = {}

    def get(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(guild)
        return self.players[guild.id]
