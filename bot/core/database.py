from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
  guild_id INTEGER PRIMARY KEY,
  prefix TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  moderator_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  reason TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS warnings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  moderator_id INTEGER NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS xp (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  amount INTEGER NOT NULL DEFAULT 0,
  last_message_at REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS economy (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  wallet INTEGER NOT NULL DEFAULT 0,
  bank INTEGER NOT NULL DEFAULT 0,
  inventory TEXT NOT NULL DEFAULT '[]',
  last_daily TEXT,
  last_weekly TEXT,
  PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS afk (
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS giveaways (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  channel_id INTEGER NOT NULL,
  message_id INTEGER,
  prize TEXT NOT NULL,
  winners INTEGER NOT NULL,
  ends_at REAL NOT NULL,
  host_id INTEGER NOT NULL,
  ended INTEGER NOT NULL DEFAULT 0,
  entries TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS tickets (
  channel_id INTEGER PRIMARY KEY,
  guild_id INTEGER NOT NULL,
  opener_id INTEGER NOT NULL,
  claimed_by INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS temp_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  expires_at REAL NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  actor_id INTEGER,
  target_id INTEGER,
  event TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS backup_codes (
  code TEXT PRIMARY KEY,
  guild_id INTEGER NOT NULL,
  creator_id INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._sqlite_path = self._parse_sqlite_path(database_url)
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_sqlite_path(url: str) -> Path:
        if url.startswith("sqlite:///"):
            return Path(url.removeprefix("sqlite:///"))
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            raise RuntimeError("PostgreSQL URL detected. Install asyncpg support and adapt Database for your deployment.")
        return Path(url)

    async def init(self) -> None:
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._sqlite_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._lock:
            async with aiosqlite.connect(self._sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA foreign_keys=ON")
                yield db
                await db.commit()

    async def fetchrow(self, query: str, *args: Any) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cur = await db.execute(query, args)
            return await cur.fetchone()

    async def fetchall(self, query: str, *args: Any) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cur = await db.execute(query, args)
            return await cur.fetchall()

    async def execute(self, query: str, *args: Any) -> int:
        async with self.connect() as db:
            cur = await db.execute(query, args)
            return cur.lastrowid

    async def get_settings(self, guild_id: int, default_prefix: str) -> dict[str, Any]:
        row = await self.fetchrow("SELECT prefix, data FROM guild_settings WHERE guild_id=?", guild_id)
        if row is None:
            await self.execute(
                "INSERT OR IGNORE INTO guild_settings(guild_id, prefix, data) VALUES(?, ?, ?)",
                guild_id,
                default_prefix,
                "{}",
            )
            row = await self.fetchrow("SELECT prefix, data FROM guild_settings WHERE guild_id=?", guild_id)
            if row is None:
                return {"prefix": default_prefix}
        data = json.loads(row["data"] or "{}")
        data["prefix"] = row["prefix"]
        return data

    async def set_settings_value(self, guild_id: int, key: str, value: Any, default_prefix: str) -> None:
        settings = await self.get_settings(guild_id, default_prefix)
        settings[key] = value
        prefix = settings.pop("prefix", default_prefix)
        await self.execute(
            "INSERT INTO guild_settings(guild_id, prefix, data) VALUES(?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET prefix=excluded.prefix, data=excluded.data",
            guild_id,
            prefix,
            json.dumps(settings),
        )

    async def set_prefix(self, guild_id: int, prefix: str, default_prefix: str) -> None:
        settings = await self.get_settings(guild_id, default_prefix)
        settings.pop("prefix", None)
        await self.execute(
            "INSERT INTO guild_settings(guild_id, prefix, data) VALUES(?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET prefix=excluded.prefix, data=excluded.data",
            guild_id,
            prefix,
            json.dumps(settings),
        )

    def backup_to(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(self._sqlite_path)
        try:
            target = sqlite3.connect(destination)
            with target:
                source.backup(target)
            target.close()
        finally:
            source.close()
