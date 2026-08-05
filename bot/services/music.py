from __future__ import annotations

import asyncio
import ctypes.util
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import discord
import imageio_ffmpeg
import yt_dlp


FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def ytdl_options() -> dict:
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": False,
        "default_search": os.getenv("YTDLP_SEARCH_PROVIDER", "ytsearch"),
        "extract_flat": False,
    }
    cookie_file = os.getenv("YTDLP_COOKIES_FILE")
    cookie_text = os.getenv("YTDLP_COOKIES_TEXT")
    if cookie_file:
        opts["cookiefile"] = cookie_file
    elif cookie_text:
        path = Path(tempfile.gettempdir()) / "yt-dlp-cookies.txt"
        path.write_text(cookie_text.replace("\\n", "\n"), encoding="utf-8")
        opts["cookiefile"] = str(path)
    return opts


def ffmpeg_executable() -> str:
    return os.getenv("FFMPEG_PATH") or imageio_ffmpeg.get_ffmpeg_exe()


def ensure_opus_loaded() -> None:
    if discord.opus.is_loaded():
        return
    opus_path = os.getenv("OPUS_PATH") or ctypes.util.find_library("opus")
    names = [opus_path, "libopus.so.0", "libopus.so", "opus"]
    for name in names:
        if not name:
            continue
        try:
            discord.opus.load_opus(name)
        except OSError:
            continue
        if discord.opus.is_loaded():
            return


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
        self.loop_one = False
        self.loop_queue = False
        self.volume = 0.6

    async def resolve(self, query: str, requester_id: int) -> list[Track]:
        def run() -> dict:
            with yt_dlp.YoutubeDL(ytdl_options()) as ytdl:
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
        ensure_opus_loaded()
        audio = discord.FFmpegPCMAudio(track.url, executable=ffmpeg_executable(), **FFMPEG_OPTS)
        return discord.PCMVolumeTransformer(audio, volume=self.volume)


class MusicManager:
    def __init__(self) -> None:
        self.players: dict[int, GuildPlayer] = {}

    def get(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(guild)
        return self.players[guild.id]
