from __future__ import annotations

import datetime as dt
import random
import re
import secrets
import string
import time
from typing import Iterable

import discord


DEFAULT_COLOR = discord.Color.from_rgb(170, 22, 38)
DARK_PURPLE = discord.Color.from_rgb(39, 18, 76)
LIGHT_PURPLE = discord.Color.from_rgb(183, 151, 255)
WHITE = discord.Color.from_rgb(245, 242, 255)
GLASS_RED = discord.Color.from_rgb(170, 22, 38)
DEEP_RED = discord.Color.from_rgb(55, 8, 14)
MULTICOLOR_FADE_COLORS = (
    (255, 56, 100),
    (183, 92, 255),
    (32, 211, 255),
    (66, 255, 158),
    (255, 203, 71),
)
PURPLE_LINES = (
    "red glass",
    "white outline",
    "crimson mist",
    "soft red glow",
    "frosted frame",
)
GLOW_BARS = (
    "[=---------]",
    "[===-------]",
    "[=====-----]",
    "[=======---]",
    "[========= ]",
    "[---=======]",
    "[-----=====]",
    "[-------===]",
)
SPARK_LINES = (
    "/\\  /\\  /\\",
    "--==--==--",
    "<<<<>>>>",
    "///|||\\\\\\",
    "==--==--==",
)


def embed(title: str, description: str | None = None, color: discord.Color = DEFAULT_COLOR) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
    e.set_footer(text=f"AinBot | {random.choice(PURPLE_LINES)}")
    return e


def is_multicolor_theme(value: str) -> bool:
    return value.strip().lower() in {"fade", "rainbow", "multi", "multicolor", "multi_color", "aurora"}


def multicolor_fade_color(speed: float = 10.0) -> discord.Color:
    position = time.time() / max(speed, 1.0)
    index = int(position) % len(MULTICOLOR_FADE_COLORS)
    next_index = (index + 1) % len(MULTICOLOR_FADE_COLORS)
    blend = position - int(position)
    start = MULTICOLOR_FADE_COLORS[index]
    end = MULTICOLOR_FADE_COLORS[next_index]
    rgb = tuple(round(start[i] + (end[i] - start[i]) * blend) for i in range(3))
    return discord.Color.from_rgb(*rgb)


def theme_color_from_data(theme: dict | None, fallback: discord.Color = DEFAULT_COLOR) -> discord.Color:
    theme = theme or {}
    if str(theme.get("mode", "")).lower() in {"fade", "rainbow", "multicolor", "aurora"}:
        return multicolor_fade_color(float(theme.get("fade_speed", 10) or 10))
    color = theme.get("color")
    if color is not None:
        try:
            return discord.Color(int(color))
        except (TypeError, ValueError):
            return fallback
    return fallback


def glow_bar() -> str:
    return random.choice(GLOW_BARS)


def spark_line() -> str:
    return random.choice(SPARK_LINES)


def flash_text(label: str = "live") -> str:
    return f"`{label}` {glow_bar()} {random.choice(PURPLE_LINES)}"


def style_embed(e: discord.Embed, *, banner_url: str | None = None, thumbnail_url: str | None = None, flashy: bool = True) -> discord.Embed:
    if flashy:
        e.add_field(name="Glass Frame", value=f"white outline // barely red glass\n{spark_line()}\n{flash_text('pulse')}", inline=False)
    if banner_url:
        e.set_image(url=banner_url)
    if thumbnail_url:
        e.set_thumbnail(url=thumbnail_url)
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
        "red": GLASS_RED,
        "glassred": GLASS_RED,
        "glass_red": GLASS_RED,
        "deepred": DEEP_RED,
        "deep_red": DEEP_RED,
        "fade": multicolor_fade_color(),
        "rainbow": multicolor_fade_color(),
        "multicolor": multicolor_fade_color(),
        "aurora": multicolor_fade_color(),
    }
    if value.strip().lower() in named:
        return named[value.strip().lower()]
    if not re.fullmatch(r"[0-9a-f]{6}", cleaned):
        raise ValueError("Use a hex color like #aa1626, red, glassred, deepred, white, or fade.")
    return discord.Color(int(cleaned, 16))


def pulse_line() -> str:
    return random.choice(
        (
            f"`glass` red panel online {glow_bar()}",
            f"`outline` white frame refreshed {spark_line()}",
            f"`pulse` crimson detail active {glow_bar()}",
            f"`shine` frosted button mode {spark_line()}",
            f"`aura` red glass interface upgraded {glow_bar()}",
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
