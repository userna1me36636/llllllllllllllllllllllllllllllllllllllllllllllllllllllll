from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import discord
import imageio_ffmpeg
import yt_dlp


FFMPEG_OPTS = {
    "before_options": "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 -reconnect_delay_max 5",
    "options": "-vn -loglevel warning",
}


def ytdl_options() -> dict:
    opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": False,
        "default_search": os.getenv("YTDLP_SEARCH_PROVIDER", "ytsearch"),
        "extract_flat": False,
        "js_runtimes": {"deno": {}},
        "extractor_args": {"youtube": {"player_client": ["default", "ios"]}},
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


def ffmpeg_candidates() -> list[str]:
    candidates = [
        os.getenv("FFMPEG_PATH"),
        shutil.which("ffmpeg"),
        imageio_ffmpeg.get_ffmpeg_exe(),
    ]
    seen: set[str] = set()
    found: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return found


def ffmpeg_executable(mode: int = 0) -> str:
    candidates = ffmpeg_candidates()
    if not candidates:
        return "ffmpeg"
    return candidates[min(mode, len(candidates) - 1)]


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

    def source(self, track: Track, mode: int = 0) -> discord.AudioSource:
        options = "-vn -loglevel warning"
        before_options = FFMPEG_OPTS["before_options"]
        if mode >= 2:
            before_options = "-nostdin"
        if mode == 0:
            return discord.FFmpegOpusAudio.from_probe(
                track.url,
                method="fallback",
                executable=ffmpeg_executable(mode),
                before_options=before_options,
                options=options,
                bitrate=128,
            )
        return discord.FFmpegOpusAudio(
            track.url,
            executable=ffmpeg_executable(mode),
            before_options=before_options,
            options=options,
            bitrate=128,
        )


class MusicManager:
    def __init__(self) -> None:
        self.players: dict[int, GuildPlayer] = {}

    def get(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(guild)
        return self.players[guild.id]
