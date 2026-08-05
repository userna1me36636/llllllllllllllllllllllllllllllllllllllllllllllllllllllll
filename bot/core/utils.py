from __future__ import annotations

import datetime as dt
import random
import re
import secrets
import string
from typing import Iterable

import discord


DEFAULT_COLOR = discord.Color.from_rgb(118, 72, 255)
DARK_PURPLE = discord.Color.from_rgb(39, 18, 76)
LIGHT_PURPLE = discord.Color.from_rgb(183, 151, 255)
WHITE = discord.Color.from_rgb(245, 242, 255)
PURPLE_LINES = (
    "midnight purple",
    "violet glow",
    "royal pulse",
    "neon lavender",
    "shadow violet",
)


def embed(title: str, description: str | None = None, color: discord.Color = DEFAULT_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    e.set_footer(text=f"AinBot | {random.choice(PURPLE_LINES)}")
    return e


def parse_color(value: str) -> discord.Color:
    cleaned = value.strip().lower().replace("#", "").replace("0x", "")
    named = {
        "purple": DEFAULT_COLOR,
        "darkpurple": DARK_PURPLE,
        "dark_purple": DARK_PURPLE,
        "lightpurple": LIGHT_PURPLE,
        "light_purple": LIGHT_PURPLE,
        "white": WHITE,
    }
    if value.strip().lower() in named:
        return named[value.strip().lower()]
    if not re.fullmatch(r"[0-9a-f]{6}", cleaned):
        raise ValueError("Use a hex color like #7648ff, or purple, darkpurple, lightpurple, white.")
    return discord.Color(int(cleaned, 16))


def pulse_line() -> str:
    return random.choice(
        (
            "`midnight` violet lighting online",
            "`glow` interface refreshed",
            "`pulse` purple detail active",
            "`shine` clean panel mode",
            "`aura` server style upgraded",
        )
    )


def parse_duration(value: str) -> dt.timedelta:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    match = re.fullmatch(r"(\d+)([smhdw])", value.strip().lower())
    if not match:
        raise ValueError("Use a duration like 10m, 2h, 7d, or 1w.")
    amount, unit = match.groups()
    return dt.timedelta(seconds=int(amount) * units[unit])


def human_join(values: Iterable[str]) -> str:
    values = list(values)
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def random_code(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def progress_bar(current: int, total: int, size: int = 14) -> str:
    if total <= 0:
        total = 1
    filled = max(0, min(size, round(size * current / total)))
    return "[" + "=" * filled + "-" * (size - filled) + "]"


def xp_for_level(level: int) -> int:
    return 100 * level * level


def level_for_xp(xp: int) -> int:
    level = 0
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level
