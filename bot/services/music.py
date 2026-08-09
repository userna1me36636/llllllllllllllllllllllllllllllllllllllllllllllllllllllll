from __future__ import annotations

import asyncio
import base64
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
        "format": os.getenv("YTDLP_FORMAT", "ba[ext=m4a]/ba[acodec^=mp4a]/bestaudio/best"),
        "quiet": True,
        "noplaylist": False,
        "default_search": os.getenv("YTDLP_SEARCH_PROVIDER", "ytsearch"),
        "extract_flat": False,
        "js_runtimes": {"deno": {}},
    }
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()
    cookie_text = os.getenv("YTDLP_COOKIES_TEXT", "").strip()
    cookie_base64 = os.getenv("YTDLP_COOKIES_BASE64", "").strip()
    if cookie_file and Path(cookie_file).is_file():
        opts["cookiefile"] = cookie_file
    elif cookie_base64 or cookie_text:
        path = Path(tempfile.gettempdir()) / "yt-dlp-cookies.txt"
        if cookie_base64:
            try:
                contents = base64.b64decode(cookie_base64, validate=True).decode("utf-8-sig")
            except (ValueError, UnicodeDecodeError) as exc:
                raise RuntimeError("YTDLP_COOKIES_BASE64 is not valid base64-encoded UTF-8 cookies.txt data.") from exc
        else:
            contents = cookie_text.strip('"\'').replace("\\r\\n", "\n").replace("\\n", "\n")
        if "# Netscape HTTP Cookie File" not in contents and not contents.lstrip().startswith("# HTTP Cookie File"):
            raise RuntimeError("YouTube cookies must use Netscape cookies.txt format.")
        path.write_text(contents.replace("\r\n", "\n"), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
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
    local_path: str | None = None
    uploader: str | None = None
    thumbnail: str | None = None
    view_count: int | None = None
    fallback_used: bool = False


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
            tracks.append(
                Track(
                    item.get("title", "Unknown track"),
                    item["url"],
                    item.get("webpage_url", query),
                    requester_id,
                    item.get("duration"),
                    None,
                    item.get("uploader") or item.get("channel"),
                    item.get("thumbnail"),
                    item.get("view_count"),
                )
            )
        return tracks

    async def download_track(self, track: Track) -> str:
        if track.local_path and Path(track.local_path).exists():
            return track.local_path

        def run() -> str:
            out_dir = Path(tempfile.gettempdir()) / "ainbot-music-cache"
            out_dir.mkdir(parents=True, exist_ok=True)
            opts = ytdl_options()
            opts.update(
                {
                    "format": os.getenv("YTDLP_DOWNLOAD_FORMAT", "ba[ext=m4a]/ba[acodec^=mp4a]/bestaudio/best"),
                    "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
                    "noplaylist": True,
                    "quiet": True,
                }
            )
            with yt_dlp.YoutubeDL(opts) as ytdl:
                info = ytdl.extract_info(track.webpage_url, download=True)
                return ytdl.prepare_filename(info)

        track.local_path = await asyncio.to_thread(run)
        return track.local_path

    async def switch_to_soundcloud(self, track: Track) -> bool:
        if track.fallback_used:
            return False

        def run() -> dict | None:
            opts = ytdl_options()
            opts.update({"noplaylist": True, "quiet": True})
            with yt_dlp.YoutubeDL(opts) as ytdl:
                data = ytdl.extract_info(f"scsearch1:{track.title}", download=False)
            entries = data.get("entries") or []
            return next((entry for entry in entries if entry and entry.get("url")), None)

        info = await asyncio.to_thread(run)
        track.fallback_used = True
        if not info:
            return False
        track.url = info["url"]
        track.webpage_url = info.get("webpage_url") or info.get("original_url") or track.webpage_url
        track.duration = info.get("duration") or track.duration
        track.uploader = info.get("uploader") or track.uploader
        track.thumbnail = info.get("thumbnail") or track.thumbnail
        track.local_path = None
        return True

    def source(self, track: Track, mode: int = 0) -> discord.AudioSource:
        options = "-vn -loglevel warning"
        before_options = FFMPEG_OPTS["before_options"]
        if mode >= 2:
            before_options = "-nostdin"
        source_url = track.local_path if track.local_path else track.url
        if track.local_path:
            before_options = "-nostdin"
        if mode == 0:
            return discord.FFmpegOpusAudio.from_probe(
                source_url,
                method="fallback",
                executable=ffmpeg_executable(mode),
                before_options=before_options,
                options=options,
                bitrate=128,
            )
        return discord.FFmpegOpusAudio(
            source_url,
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
