from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


def _ids(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(part.strip()) for part in value.split(",") if part.strip().isdigit()}


def _tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()][:20]


@dataclass(slots=True)
class Settings:
    discord_token: str
    database_url: str
    default_prefix: str
    owner_ids: set[int]
    log_level: str
    backup_interval_minutes: int
    enable_music: bool
    ytdlp_search_provider: str
    spotify_client_id: str | None
    spotify_client_secret: str | None
    openweather_api_key: str | None
    deepl_api_key: str | None
    openai_api_key: str | None
    backup_webhook_url: str | None
    auto_sync_commands: bool
    companion_bot_tokens: list[str]

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token == "put-your-token-here":
            raise RuntimeError("Set DISCORD_TOKEN in .env before starting the bot.")
        return cls(
            discord_token=token,
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'bot.sqlite3'}"),
            default_prefix=os.getenv("DEFAULT_PREFIX", "!"),
            owner_ids=_ids(os.getenv("OWNER_IDS")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            backup_interval_minutes=int(os.getenv("BACKUP_INTERVAL_MINUTES", "720")),
            enable_music=_bool(os.getenv("ENABLE_MUSIC"), True),
            ytdlp_search_provider=os.getenv("YTDLP_SEARCH_PROVIDER", "ytsearch"),
            spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID") or None,
            spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET") or None,
            openweather_api_key=os.getenv("OPENWEATHER_API_KEY") or None,
            deepl_api_key=os.getenv("DEEPL_API_KEY") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            backup_webhook_url=os.getenv("BACKUP_WEBHOOK_URL") or None,
            auto_sync_commands=_bool(os.getenv("AUTO_SYNC_COMMANDS"), False),
            companion_bot_tokens=_tokens(os.getenv("COMPANION_BOT_TOKENS")),
        )
