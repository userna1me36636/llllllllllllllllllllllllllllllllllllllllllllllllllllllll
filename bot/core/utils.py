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


def embed(title: str, description: str | None = None, color: discord.Color = DEFAULT_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    e.set_footer(text="AinBot • dark purple system")
    return e


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
