import asyncio
import hashlib
import hmac
import json
import os
import random
import re
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import discord
import yt_dlp
from aiohttp import web
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv


# ====================== DASHBOARD CONFIG (WEBSITE) ======================
CONFIG_PATH = os.getenv("BOT_CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.json"))

def get_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("command_prefixes", {})
            data.setdefault("premium", {})
            return data
    except Exception:
        return {"prefix": "!", "command_prefixes": {}, "owners": [], "premium": {}}


def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_prefix(bot, message):
    """Returns the default prefix. Per-command prefixes are handled in on_message if needed."""
    return get_config().get("prefix", "!")

def get_command_prefix(command_name: str) -> str:
    """Get the prefix for a specific command (falls back to default)."""
    config = get_config()
    custom = config.get("command_prefixes", {}).get(command_name)
    return custom if custom else config.get("prefix", "!")

def is_owner(user_id: int) -> bool:
    owners = get_config().get("owners", [])
    return str(user_id) in [str(o) for o in owners]


def premium_config() -> dict:
    """Configuration is intentionally empty by default: payment must be verified externally."""
    return get_config().get("premium", {})


def payment_url(tier: str) -> str:
    return str(premium_config().get("payment_urls", {}).get(tier, "")).strip()


class PurchaseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        labels = (("vc", "VC perms — $25"), ("godmode", "God Mode — $35"), ("both", "Both — $50"))
        for tier, label in labels:
            url = payment_url(tier)
            if url.startswith(("https://", "http://")):
                self.add_item(discord.ui.Button(label=label, url=url))


async def send_purchase_dm(member: discord.Member) -> None:
    if not any(payment_url(tier) for tier in ("vc", "godmode", "both")):
        return
    try:
        await member.send("You were removed from a voice channel. Antikick Premium is available:", view=PurchaseView())
    except (discord.Forbidden, discord.HTTPException):
        pass
# ========================================================================


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = Path(os.getenv("BOT_DATA_DIR", BASE_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "bot_data.sqlite3"

load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
MAX_MUSIC_VOICE_CLIENTS = int(os.getenv("MAX_MUSIC_VOICE_CLIENTS", "5"))
CHAT_REVIVE_INTERVAL_MINUTES = int(os.getenv("CHAT_REVIVE_INTERVAL_MINUTES", "120"))
DEFAULT_ANTINUKE_PUNISHMENT = os.getenv("DEFAULT_ANTINUKE_PUNISHMENT", "strip").lower()

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True
INTENTS.guilds = True
INTENTS.voice_states = True
INTENTS.messages = True
INTENTS.moderation = True

bot = commands.Bot(command_prefix=get_prefix, intents=INTENTS, help_command=None)
synced_once = False
last_message_by_channel: dict[int, float] = {}
raid_hits: dict[tuple[int, int, str], deque[float]] = defaultdict(deque)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                antinuke_enabled INTEGER DEFAULT 0,
                antinuke_punishment TEXT DEFAULT 'strip',
                chat_revive_channel_id INTEGER,
                chat_revive_message TEXT,
                chat_revive_interval_minutes INTEGER DEFAULT 120,
                chat_revive_enabled INTEGER DEFAULT 0,
                jtc_category_id INTEGER,
                jtc_lobby_id INTEGER,
                welcome_channel_id INTEGER,
                welcome_message TEXT,
                leave_channel_id INTEGER,
                leave_message TEXT,
                log_channel_id INTEGER,
                log_webhook_url TEXT,
                autorole_id INTEGER,
                automod_invites INTEGER DEFAULT 0,
                automod_links INTEGER DEFAULT 0,
                automod_words TEXT,
                levels_enabled INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                remind_at INTEGER NOT NULL,
                text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS temp_voice (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vc_godmode (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                enabled_by INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS premium_purchases (
                purchase_id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                tier TEXT NOT NULL,
                verified_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS levels (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER DEFAULT 0,
                last_xp_at INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, emoji)
            );
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                prize TEXT NOT NULL,
                winner_count INTEGER NOT NULL,
                ends_at INTEGER NOT NULL,
                ended INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
        """)


def ensure_guild_row(guild_id: int) -> sqlite3.Row:
    with db() as con:
        con.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id, antinuke_punishment, chat_revive_interval_minutes) VALUES (?, ?, ?)",
            (guild_id, DEFAULT_ANTINUKE_PUNISHMENT, CHAT_REVIVE_INTERVAL_MINUTES),
        )
        return con.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()


def human_dt(ts: int) -> str:
    return f"<t:{ts}:R> (<t:{ts}:f>)"


async def send_ok(interaction: discord.Interaction, text: str, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(text, ephemeral=ephemeral)


def parse_duration(text: str) -> Optional[int]:
    text = text.strip().lower().replace(" ", "")
    if text.isdigit():
        return int(text) * 60
    total = 0
    matches = re.findall(r"(\d+)(w|d|h|m|s)", text)
    if not matches:
        return None
    multipliers = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    for amount, unit in matches:
        total += int(amount) * multipliers[unit]
    return total if total > 0 else None


def level_for_xp(xp: int) -> int:
    return int((xp / 100) ** 0.5)


DANGEROUS_PERMISSIONS = {
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "ban_members", "kick_members", "moderate_members",
    "manage_messages", "mention_everyone"
}


def dangerous_permission_names(permissions: discord.Permissions) -> list[str]:
    return [name for name in DANGEROUS_PERMISSIONS if getattr(permissions, name, False)]


def role_has_dangerous_permissions(role: discord.Role) -> bool:
    return bool(dangerous_permission_names(role.permissions))


async def log_event(guild: discord.Guild, title: str, description: str, color: discord.Color = discord.Color.blurple()) -> None:
    row = ensure_guild_row(guild.id)
    channel_id = row["log_channel_id"]
    channel = guild.get_channel(channel_id) if channel_id else None
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except:
            pass


async def punish_member(guild: discord.Guild, member: discord.Member, reason: str, mode: str) -> None:
    if member.id == guild.owner_id or is_owner(member.id):
        return
    try:
        if mode == "strip":
            roles = [r for r in member.roles if r != guild.default_role and r < guild.me.top_role and role_has_dangerous_permissions(r)]
            if roles:
                await member.remove_roles(*roles, reason=reason)
            await log_event(guild, "Anti-Nuke", f"{member.mention} → stripped dangerous roles\nReason: {reason}", discord.Color.red())
        elif mode == "ban":
            await member.ban(reason=reason)
            await log_event(guild, "Anti-Nuke", f"{member.mention} was banned\nReason: {reason}", discord.Color.red())
        elif mode == "timeout":
            await member.timeout(timedelta(days=1), reason=reason)
            await log_event(guild, "Anti-Nuke", f"{member.mention} was timed out\nReason: {reason}", discord.Color.red())
        else:
            await member.kick(reason=reason)
            await log_event(guild, "Anti-Nuke", f"{member.mention} was kicked\nReason: {reason}", discord.Color.red())
    except discord.Forbidden:
        await log_event(guild, "Anti-Nuke Failed", f"Could not punish {member.mention}. Move my role higher.", discord.Color.dark_red())


async def audit_actor(guild: discord.Guild, action: discord.AuditLogAction, target_id: Optional[int] = None) -> Optional[discord.Member]:
    try:
        async for entry in guild.audit_logs(limit=6, action=action):
            if target_id is None or getattr(entry.target, "id", None) == target_id:
                if isinstance(entry.user, discord.Member):
                    return entry.user
                return guild.get_member(entry.user.id)
    except:
        return None
    return None


async def antinuke_check(guild: discord.Guild, actor: Optional[discord.Member], action_name: str, limit: int = 3, window: int = 30) -> None:
    if actor is None or (actor.bot and actor.id == bot.user.id):
        return
    settings = ensure_guild_row(guild.id)
    if not settings["antinuke_enabled"]:
        return
    if actor.id == guild.owner_id or is_owner(actor.id):
        return
    key = (guild.id, actor.id, action_name)
    now = time.time()
    bucket = raid_hits[key]
    bucket.append(now)
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        mode = settings["antinuke_punishment"] if settings["antinuke_punishment"] in {"strip", "ban", "timeout"} else "strip"
        await punish_member(guild, actor, f"Anti-nuke: {action_name}", mode)
        bucket.clear()


# ====================== PREMIUM PAYMENT WEBHOOK ======================

PREMIUM_PRICES = {"vc": 2500, "godmode": 3500, "both": 5000}

async def grant_premium(guild_id: int, user_id: int, tier: str, purchase_id: str) -> str:
    """Grant only after a signed payment-success webhook; repeated IDs are safe."""
    with db() as con:
        if con.execute("SELECT 1 FROM premium_purchases WHERE purchase_id = ?", (purchase_id,)).fetchone():
            return "already processed"
    guild = bot.get_guild(guild_id)
    if not guild:
        raise ValueError("Guild is unavailable to the bot")
    member = guild.get_member(user_id) or await guild.fetch_member(user_id)
    role_ids = premium_config().get("role_ids", {})
    wanted = ([role_ids.get("vc")] if tier in {"vc", "both"} else []) + ([role_ids.get("godmode")] if tier in {"godmode", "both"} else [])
    roles = [guild.get_role(int(role_id)) for role_id in wanted if str(role_id or "").isdigit()]
    roles = [role for role in roles if role]
    if wanted and len(roles) != len(wanted):
        raise ValueError("A configured premium role was not found in this guild")
    if roles:
        await member.add_roles(*roles, reason=f"Verified Antikick Premium purchase {purchase_id}")
    if tier in {"godmode", "both"}:
        with db() as con:
            con.execute("INSERT OR REPLACE INTO vc_godmode (guild_id, user_id, enabled_by, created_at) VALUES (?, ?, ?, ?)", (guild_id, user_id, bot.user.id if bot.user else 0, int(time.time())))
    with db() as con:
        con.execute("INSERT INTO premium_purchases (purchase_id, guild_id, user_id, tier, verified_at) VALUES (?, ?, ?, ?, ?)", (purchase_id, guild_id, user_id, tier, int(time.time())))
    try:
        await member.send("Payment verified. Your Antikick Premium access is active.")
    except (discord.Forbidden, discord.HTTPException):
        pass
    return "granted"

async def premium_webhook(request: web.Request) -> web.Response:
    secret = os.getenv("PREMIUM_WEBHOOK_SECRET", str(premium_config().get("webhook_secret", "")))
    raw, signature = await request.read(), request.headers.get("X-Antikick-Signature", "")
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest() if secret else ""
    if not secret or not hmac.compare_digest(signature, expected):
        return web.json_response({"error": "Invalid signature"}, status=401)
    try:
        payload = json.loads(raw)
        tier, purchase_id = payload["tier"], str(payload["purchase_id"])
        guild_id, user_id = int(payload["guild_id"]), int(payload["discord_user_id"])
        if payload.get("event") != "payment.succeeded" or tier not in PREMIUM_PRICES or int(payload.get("amount_cents", 0)) != PREMIUM_PRICES[tier]:
            raise ValueError("Invalid payment event")
        return web.json_response({"ok": True, "result": await grant_premium(guild_id, user_id, tier, purchase_id)})
    except (KeyError, TypeError, ValueError, discord.HTTPException, discord.NotFound) as error:
        return web.json_response({"error": str(error)}, status=400)

def dashboard_authorized(request: web.Request) -> bool:
    key = request.query.get("key") or request.headers.get("X-Access-Key", "")
    expected = os.getenv("DASHBOARD_ACCESS_KEY", str(get_config().get("accessKey", "")))
    return bool(key) and hmac.compare_digest(expected, key)

async def dashboard_config(request: web.Request) -> web.Response:
    if not dashboard_authorized(request):
        return web.json_response({"error": "Invalid access key"}, status=401)
    config = get_config()
    return web.json_response({
        "prefix": config.get("prefix", "!"),
        "owners": config.get("owners", []),
        "command_prefixes": config.get("command_prefixes", {}),
        "premium": config.get("premium", {}),
        "recovery": config.get("recovery", {"invite_url": ""}),
    })

async def dashboard_settings(request: web.Request) -> web.Response:
    if not dashboard_authorized(request):
        return web.json_response({"error": "Invalid access key"}, status=401)
    try:
        data = await request.json()
        prefix = str(data.get("prefix", "")).strip()
        urls, roles, recovery = data.get("payment_urls", {}), data.get("role_ids", {}), data.get("recovery", {})
        if not prefix or len(prefix) > 10:
            raise ValueError("Prefix must be 1–10 characters.")
        for url in (urls.get("vc", ""), urls.get("godmode", ""), urls.get("both", ""), recovery.get("invite_url", "")):
            if url and not str(url).startswith("https://"):
                raise ValueError("Use HTTPS links.")
        for role_id in (roles.get("vc", ""), roles.get("godmode", "")):
            if role_id and not re.fullmatch(r"\d{17,20}", str(role_id)):
                raise ValueError("Enter valid Discord role IDs.")
        config = get_config()
        config["prefix"] = prefix
        config["premium"] = {**config.get("premium", {}), "payment_urls": {tier: str(urls.get(tier, "")) for tier in ("vc", "godmode", "both")}, "role_ids": {tier: str(roles.get(tier, "")) for tier in ("vc", "godmode")}}
        config["recovery"] = {"invite_url": str(recovery.get("invite_url", ""))}
        save_config(config)
        return web.json_response({"ok": True})
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        return web.json_response({"error": str(error)}, status=400)

async def dashboard_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")

async def start_web_service() -> None:
    if getattr(bot, "web_runner", None):
        return
    port = int(os.getenv("PORT", os.getenv("PREMIUM_WEBHOOK_PORT", "8080")))
    app = web.Application()
    app.router.add_post("/webhooks/premium", premium_webhook)
    app.router.add_get("/api/config", dashboard_config)
    app.router.add_post("/api/settings", dashboard_settings)
    app.router.add_get("/{path:.*}", dashboard_page)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    bot.web_runner = runner
    print(f"Dashboard and premium webhook listening on port {port}")


# ====================== EVENTS ======================

@bot.event
async def on_ready() -> None:
    global synced_once
    init_db()
    await start_web_service()
    for loop in (reminder_loop, chat_revive_loop, cleanup_temp_voice_loop, giveaway_loop):
        if not loop.is_running():
            loop.start()
    if not synced_once:
        print("=" * 55)
        print(f"Bot online as {bot.user} ({bot.user.id})")
        print("Prefix & Owners controlled by the website dashboard")
        print("=" * 55)
        for guild in bot.guilds:
            try:
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                print(f"Synced {len(synced)} commands → {guild.name}")
            except Exception as e:
                print(f"Sync error: {guild.name} → {e}")
        synced_once = True


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.guild and not message.author.bot:
        last_message_by_channel[message.channel.id] = time.time()
        settings = ensure_guild_row(message.guild.id)

        lowered = message.content.lower()
        should_delete = False
        reason = None
        if settings["automod_invites"] and re.search(r"(discord\.gg/|discord\.com/invite/)", lowered):
            should_delete = True
            reason = "Discord invite blocked"
        if settings["automod_links"] and re.search(r"https?://|www\.", lowered):
            should_delete = True
            reason = "Link blocked"
        banned_words = [w.strip().lower() for w in (settings["automod_words"] or "").split(",") if w.strip()]
        if banned_words and any(w in lowered for w in banned_words):
            should_delete = True
            reason = "Banned word blocked"
        if should_delete and isinstance(message.channel, discord.TextChannel):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, {reason}.", delete_after=6)
            except:
                pass
            return

        if settings["levels_enabled"]:
            now = int(time.time())
            with db() as con:
                row = con.execute("SELECT xp, last_xp_at FROM levels WHERE guild_id = ? AND user_id = ?",
                                  (message.guild.id, message.author.id)).fetchone()
                old_xp = row["xp"] if row else 0
                if not row or now - row["last_xp_at"] >= 60:
                    new_xp = old_xp + 15
                    con.execute("INSERT OR REPLACE INTO levels (guild_id, user_id, xp, last_xp_at) VALUES (?, ?, ?, ?)",
                                (message.guild.id, message.author.id, new_xp, now))
                    if level_for_xp(new_xp) > level_for_xp(old_xp):
                        try:
                            await message.channel.send(f"{message.author.mention} leveled up to **{level_for_xp(new_xp)}**!")
                        except:
                            pass
    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member) -> None:
    if member.bot:
        actor = await audit_actor(member.guild, discord.AuditLogAction.bot_add, member.id)
        await antinuke_check(member.guild, actor, "bot_add", limit=1)
    settings = ensure_guild_row(member.guild.id)
    if settings["autorole_id"]:
        role = member.guild.get_role(settings["autorole_id"])
        if role:
            try:
                await member.add_roles(role, reason="Autorole")
            except:
                pass
    if settings["welcome_channel_id"]:
        channel = member.guild.get_channel(settings["welcome_channel_id"])
        if isinstance(channel, discord.TextChannel):
            text = (settings["welcome_message"] or "Welcome {member} to {server}!")
            text = text.replace("{member}", member.mention).replace("{server}", member.guild.name).replace("{count}", str(member.guild.member_count))
            try:
                await channel.send(text)
            except:
                pass
    await log_event(member.guild, "Member Joined", f"{member.mention} joined.", discord.Color.green())


@bot.event
async def on_member_remove(member: discord.Member) -> None:
    actor = await audit_actor(member.guild, discord.AuditLogAction.kick, member.id)
    await antinuke_check(member.guild, actor, "mass_kick")
    settings = ensure_guild_row(member.guild.id)
    if settings["leave_channel_id"]:
        channel = member.guild.get_channel(settings["leave_channel_id"])
        if isinstance(channel, discord.TextChannel):
            text = (settings["leave_message"] or "{member} left {server}.")
            text = text.replace("{member}", str(member)).replace("{server}", member.guild.name)
            try:
                await channel.send(text)
            except:
                pass
    await log_event(member.guild, "Member Left", f"{member} left the server.", discord.Color.orange())


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User) -> None:
    actor = await audit_actor(guild, discord.AuditLogAction.ban, user.id)
    await antinuke_check(guild, actor, "mass_ban")


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
    actor = await audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    await antinuke_check(channel.guild, actor, "channel_delete", limit=2)
    await log_event(channel.guild, "Channel Deleted", f"`{channel.name}` deleted by {actor.mention if actor else 'Unknown'}", discord.Color.red())


@bot.event
async def on_guild_role_delete(role: discord.Role) -> None:
    actor = await audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)
    await antinuke_check(role.guild, actor, "role_delete", limit=2)
    await log_event(role.guild, "Role Deleted", f"`{role.name}` deleted by {actor.mention if actor else 'Unknown'}", discord.Color.red())


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role) -> None:
    if before.permissions == after.permissions:
        return
    actor = await audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)
    before_d = set(dangerous_permission_names(before.permissions))
    after_d = set(dangerous_permission_names(after.permissions))
    added = sorted(after_d - before_d)
    if added:
        await antinuke_check(after.guild, actor, "dangerous_role_permission_grant", limit=1, window=60)
        await log_event(after.guild, "Dangerous Permissions Added", f"Role {after.mention}\nAdded: {', '.join(added)}\nBy: {actor.mention if actor else 'Unknown'}", discord.Color.orange())


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    added = [r for r in set(after.roles) - set(before.roles) if role_has_dangerous_permissions(r)]
    if added:
        actor = await audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
        await antinuke_check(after.guild, actor, "dangerous_role_given", limit=1, window=60)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
    if payload.guild_id is None or payload.user_id == bot.user.id:
        return
    with db() as con:
        row = con.execute("SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                          (payload.message_id, str(payload.emoji))).fetchone()
    if row:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(row["role_id"]) if guild else None
        if member and role:
            try:
                await member.add_roles(role, reason="Reaction role")
            except:
                pass


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent) -> None:
    if payload.guild_id is None:
        return
    with db() as con:
        row = con.execute("SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?",
                          (payload.message_id, str(payload.emoji))).fetchone()
    if row:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(row["role_id"]) if guild else None
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role")
            except:
                pass


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
    settings = ensure_guild_row(member.guild.id)
    lobby_id = settings["jtc_lobby_id"]
    if after.channel and after.channel.id == lobby_id:
        category = member.guild.get_channel(settings["jtc_category_id"]) if settings["jtc_category_id"] else after.channel.category
        try:
            new_channel = await member.guild.create_voice_channel(
                name=f"{member.display_name}'s Channel",
                category=category,
                reason="Join-to-create"
            )
            await member.move_to(new_channel)
            with db() as con:
                con.execute("INSERT OR REPLACE INTO temp_voice (channel_id, guild_id, owner_id) VALUES (?, ?, ?)",
                            (new_channel.id, member.guild.id, member.id))
            await new_channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
        except:
            pass


# ====================== LOOPS ======================

@tasks.loop(seconds=30)
async def reminder_loop() -> None:
    now = int(time.time())
    with db() as con:
        rows = con.execute("SELECT * FROM reminders WHERE remind_at <= ?", (now,)).fetchall()
        for row in rows:
            channel = bot.get_channel(row["channel_id"])
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(f"<@{row['user_id']}> Reminder: {row['text']}")
                except:
                    pass
            con.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))


@tasks.loop(minutes=5)
async def chat_revive_loop() -> None:
    with db() as con:
        rows = con.execute("SELECT * FROM guild_settings WHERE chat_revive_enabled = 1 AND chat_revive_channel_id IS NOT NULL").fetchall()
    for row in rows:
        channel = bot.get_channel(row["chat_revive_channel_id"])
        if not isinstance(channel, discord.TextChannel):
            continue
        last = last_message_by_channel.get(channel.id, 0)
        interval = (row["chat_revive_interval_minutes"] or 120) * 60
        if time.time() - last >= interval:
            text = row["chat_revive_message"] or "Anyone around?"
            try:
                await channel.send(text)
                last_message_by_channel[channel.id] = time.time()
            except:
                pass


@tasks.loop(minutes=2)
async def cleanup_temp_voice_loop() -> None:
    with db() as con:
        rows = con.execute("SELECT channel_id, guild_id FROM temp_voice").fetchall()
    for row in rows:
        guild = bot.get_guild(row["guild_id"])
        if not guild:
            continue
        channel = guild.get_channel(row["channel_id"])
        if not isinstance(channel, discord.VoiceChannel) or len(channel.members) == 0:
            try:
                if channel:
                    await channel.delete(reason="Empty temp VC")
            except:
                pass
            with db() as con:
                con.execute("DELETE FROM temp_voice WHERE channel_id = ?", (row["channel_id"],))


@tasks.loop(seconds=20)
async def giveaway_loop() -> None:
    now = int(time.time())
    with db() as con:
        rows = con.execute("SELECT * FROM giveaways WHERE ended = 0 AND ends_at <= ?", (now,)).fetchall()
    for row in rows:
        channel = bot.get_channel(row["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            message = await channel.fetch_message(row["message_id"])
        except:
            with db() as con:
                con.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (row["message_id"],))
            continue
        users = []
        for reaction in message.reactions:
            if str(reaction.emoji) == "🎉":
                async for user in reaction.users():
                    if not user.bot:
                        users.append(user)
                break
        winners = random.sample(users, min(row["winner_count"], len(users))) if users else []
        if winners:
            await channel.send(f"🎉 Giveaway ended! **{row['prize']}**\nWinners: {', '.join(w.mention for w in winners)}")
        else:
            await channel.send(f"🎉 Giveaway ended! **{row['prize']}**\nNo valid entries.")
        with db() as con:
            con.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ?", (row["message_id"],))


# ====================== COGS ======================

class General(commands.Cog):
    @app_commands.command(name="ping", description="Check latency")
    async def ping(self, interaction: discord.Interaction) -> None:
        await send_ok(interaction, f"Pong! `{round(bot.latency*1000)}ms`")

    @app_commands.command(name="ownercheck", description="Check if you are a website owner")
    async def ownercheck(self, interaction: discord.Interaction) -> None:
        if is_owner(interaction.user.id):
            await send_ok(interaction, "✅ You **are** a bot owner (from the website).")
        else:
            await send_ok(interaction, "❌ You are **not** listed as an owner on the website.")

    @app_commands.command(name="prefix", description="Show current prefix from the website")
    async def prefix(self, interaction: discord.Interaction) -> None:
        await send_ok(interaction, f"Current prefix: `{get_config().get('prefix', '!')}`")


class Moderation(commands.Cog):
    mod = app_commands.Group(name="mod", description="Moderation")

    @mod.command(name="kick")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason") -> None:
        if is_owner(member.id) or member.id == interaction.guild.owner_id:
            return await send_ok(interaction, "Cannot kick that member.")
        await member.kick(reason=reason)
        await send_ok(interaction, f"Kicked {member.mention}")

    @mod.command(name="ban")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason") -> None:
        if is_owner(member.id) or member.id == interaction.guild.owner_id:
            return await send_ok(interaction, "Cannot ban that member.")
        await member.ban(reason=reason)
        await send_ok(interaction, f"Banned {member.mention}")

    @mod.command(name="timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "No reason") -> None:
        seconds = parse_duration(duration)
        if not seconds:
            return await send_ok(interaction, "Invalid duration (e.g. 10m, 1h, 1d)")
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        await send_ok(interaction, f"Timed out {member.mention} for {duration}")

    @mod.command(name="warn")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason") -> None:
        with db() as con:
            con.execute("INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                        (interaction.guild_id, member.id, interaction.user.id, reason, int(time.time())))
        await send_ok(interaction, f"Warned {member.mention}: {reason}")

    @mod.command(name="warnings")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        with db() as con:
            rows = con.execute("SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 10",
                               (interaction.guild_id, member.id)).fetchall()
        if not rows:
            return await send_ok(interaction, f"{member.mention} has no warnings.")
        text = "\n".join(f"• {r['reason']} — <t:{r['created_at']}:R>" for r in rows)
        await send_ok(interaction, f"**Warnings for {member.display_name}:**\n{text}", ephemeral=False)


class AntiNuke(commands.Cog):
    antinuke = app_commands.Group(name="antinuke", description="Anti-nuke")

    @antinuke.command(name="enable")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET antinuke_enabled = 1 WHERE guild_id = ?", (interaction.guild_id,))
        await send_ok(interaction, "Anti-nuke **enabled**")

    @antinuke.command(name="disable")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET antinuke_enabled = 0 WHERE guild_id = ?", (interaction.guild_id,))
        await send_ok(interaction, "Anti-nuke **disabled**")

    @antinuke.command(name="punishment")
    @app_commands.checks.has_permissions(administrator=True)
    async def punishment(self, interaction: discord.Interaction, mode: str) -> None:
        mode = mode.lower()
        if mode not in {"strip", "kick", "ban", "timeout"}:
            return await send_ok(interaction, "Choose: strip / kick / ban / timeout")
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET antinuke_punishment = ? WHERE guild_id = ?", (mode, interaction.guild_id))
        await send_ok(interaction, f"Anti-nuke punishment set to **{mode}**")


class Levels(commands.Cog):
    @app_commands.command(name="rank", description="Show level & XP")
    async def rank(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        member = member or interaction.user
        with db() as con:
            row = con.execute("SELECT xp FROM levels WHERE guild_id = ? AND user_id = ?",
                              (interaction.guild_id, member.id)).fetchone()
        xp = row["xp"] if row else 0
        await send_ok(interaction, f"**{member.display_name}** → Level **{level_for_xp(xp)}** ({xp} XP)", ephemeral=False)

    @app_commands.command(name="leaderboard", description="Top 10 levels")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        with db() as con:
            rows = con.execute("SELECT user_id, xp FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
                               (interaction.guild_id,)).fetchall()
        if not rows:
            return await send_ok(interaction, "No data yet.")
        lines = [f"**{i}.** <@{r['user_id']}> — Level {level_for_xp(r['xp'])} ({r['xp']} XP)" for i, r in enumerate(rows, 1)]
        await send_ok(interaction, "\n".join(lines), ephemeral=False)


class Reminders(commands.Cog):
    remind = app_commands.Group(name="remind", description="Reminders")

    @remind.command(name="me", description="Set a reminder")
    async def me(self, interaction: discord.Interaction, duration: str, text: str) -> None:
        seconds = parse_duration(duration)
        if not seconds:
            return await send_ok(interaction, "Use duration like `10m`, `2h`, `1d`")
        remind_at = int(time.time() + seconds)
        with db() as con:
            con.execute("INSERT INTO reminders (user_id, channel_id, remind_at, text) VALUES (?, ?, ?, ?)",
                        (interaction.user.id, interaction.channel_id, remind_at, text))
        await send_ok(interaction, f"Reminder set for {human_dt(remind_at)}")

    @remind.command(name="list")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        with db() as con:
            rows = con.execute("SELECT * FROM reminders WHERE user_id = ? ORDER BY remind_at LIMIT 10",
                               (interaction.user.id,)).fetchall()
        if not rows:
            return await send_ok(interaction, "You have no reminders.")
        text = "\n".join(f"**#{r['id']}** {human_dt(r['remind_at'])} — {r['text']}" for r in rows)
        await send_ok(interaction, text)


class Giveaways(commands.Cog):
    giveaway = app_commands.Group(name="giveaway", description="Giveaways")

    @giveaway.command(name="start")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start(self, interaction: discord.Interaction, duration: str, winners: app_commands.Range[int, 1, 20], prize: str) -> None:
        seconds = parse_duration(duration)
        if not seconds:
            return await send_ok(interaction, "Invalid duration (e.g. 30m, 1h, 1d)")
        ends_at = int(time.time() + seconds)
        embed = discord.Embed(title="🎉 GIVEAWAY", description=f"**Prize:** {prize}\n**Winners:** {winners}\n**Ends:** {human_dt(ends_at)}\n\nReact with 🎉 to enter!", color=discord.Color.gold())
        embed.set_footer(text=f"Hosted by {interaction.user}")
        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()
        await msg.add_reaction("🎉")
        with db() as con:
            con.execute("INSERT OR REPLACE INTO giveaways (message_id, guild_id, channel_id, host_id, prize, winner_count, ends_at, ended) VALUES (?,?,?,?,?,?,?,0)",
                        (msg.id, interaction.guild_id, interaction.channel_id, interaction.user.id, prize, winners, ends_at))


class ServerSetup(commands.Cog):
    setup = app_commands.Group(name="setup", description="Server configuration")

    @setup.command(name="welcome")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Welcome {member} to {server}!") -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET welcome_channel_id = ?, welcome_message = ? WHERE guild_id = ?",
                        (channel.id, message, interaction.guild_id))
        await send_ok(interaction, f"Welcome messages will be sent in {channel.mention}")

    @setup.command(name="leave")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leave(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "{member} left {server}.") -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET leave_channel_id = ?, leave_message = ? WHERE guild_id = ?",
                        (channel.id, message, interaction.guild_id))
        await send_ok(interaction, f"Leave messages will be sent in {channel.mention}")

    @setup.command(name="autorole")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autorole(self, interaction: discord.Interaction, role: discord.Role) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET autorole_id = ? WHERE guild_id = ?", (role.id, interaction.guild_id))
        await send_ok(interaction, f"Autorole set to {role.mention}")

    @setup.command(name="logs")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET log_channel_id = ? WHERE guild_id = ?", (channel.id, interaction.guild_id))
        await send_ok(interaction, f"Log channel set to {channel.mention}")

    @setup.command(name="chatrevive")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def chatrevive(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Anyone around?", interval: int = 120) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET chat_revive_enabled = 1, chat_revive_channel_id = ?, chat_revive_message = ?, chat_revive_interval_minutes = ? WHERE guild_id = ?",
                        (channel.id, message, interval, interaction.guild_id))
        await send_ok(interaction, f"Chat revive enabled in {channel.mention} every {interval} minutes")


class Tickets(commands.Cog):
    ticket = app_commands.Group(name="ticket", description="Ticket system")

    @ticket.command(name="create", description="Create a support ticket")
    async def create(self, interaction: discord.Interaction, reason: str = "No reason given") -> None:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            reason="Ticket created"
        )
        with db() as con:
            con.execute("INSERT OR REPLACE INTO tickets (channel_id, guild_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                        (channel.id, interaction.guild_id, interaction.user.id, int(time.time())))
        await channel.send(f"{interaction.user.mention} Ticket created.\n**Reason:** {reason}\nStaff will be with you shortly.")
        await send_ok(interaction, f"Ticket created: {channel.mention}")

    @ticket.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction) -> None:
        with db() as con:
            row = con.execute("SELECT * FROM tickets WHERE channel_id = ?", (interaction.channel_id,)).fetchone()
        if not row:
            return await send_ok(interaction, "This is not a ticket channel.")
        if interaction.user.id != row["user_id"] and not interaction.user.guild_permissions.manage_channels:
            return await send_ok(interaction, "Only the ticket owner or staff can close this.")
        await send_ok(interaction, "Closing ticket in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason="Ticket closed")
        except:
            pass
        with db() as con:
            con.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel_id,))


class ReactionRoles(commands.Cog):
    rr = app_commands.Group(name="reactionrole", description="Reaction roles")

    @rr.command(name="add")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role) -> None:
        try:
            mid = int(message_id)
        except:
            return await send_ok(interaction, "Invalid message ID")
        with db() as con:
            con.execute("INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
                        (interaction.guild_id, mid, emoji, role.id))
        await send_ok(interaction, f"Reaction role added: {emoji} → {role.mention}")


# ====================== VOICEMASTER ======================

async def temp_owner(channel_id: int) -> Optional[int]:
    with db() as con:
        row = con.execute("SELECT owner_id FROM temp_voice WHERE channel_id = ?", (channel_id,)).fetchone()
    return row["owner_id"] if row else None

async def vc_godmode_enabled(guild_id: int, user_id: int) -> bool:
    with db() as con:
        return con.execute("SELECT 1 FROM vc_godmode WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone() is not None

async def require_temp_owner(interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
    if not interaction.user.voice or not isinstance(interaction.user.voice.channel, discord.VoiceChannel):
        await send_ok(interaction, "Join your temporary voice channel first.")
        return None
    channel = interaction.user.voice.channel
    owner_id = await temp_owner(channel.id)
    if owner_id and owner_id != interaction.user.id and await vc_godmode_enabled(interaction.guild_id, owner_id):
        await send_ok(interaction, "That VC owner has god mode.")
        return None
    if owner_id != interaction.user.id and not interaction.user.guild_permissions.manage_channels:
        await send_ok(interaction, "Only the temp VC owner can use this.")
        return None
    return channel


class VoiceMaster(commands.Cog):
    jtc = app_commands.Group(name="jtc", description="Join to Create")
    vc = app_commands.Group(name="vc", description="Temp VC controls")

    @jtc.command(name="setup")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup(self, interaction: discord.Interaction, category: Optional[discord.CategoryChannel] = None, name: str = "Join to Create") -> None:
        await interaction.response.defer(ephemeral=True)
        category = category or (interaction.channel.category if isinstance(interaction.channel, discord.TextChannel) else None)
        lobby = await interaction.guild.create_voice_channel(name=name, category=category)
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET jtc_category_id = ?, jtc_lobby_id = ? WHERE guild_id = ?",
                        (category.id if category else None, lobby.id, interaction.guild_id))
        await interaction.followup.send(f"Lobby created: {lobby.mention}", ephemeral=True)

    @jtc.command(name="disable")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        ensure_guild_row(interaction.guild_id)
        with db() as con:
            con.execute("UPDATE guild_settings SET jtc_lobby_id = NULL, jtc_category_id = NULL WHERE guild_id = ?", (interaction.guild_id,))
        await send_ok(interaction, "Join-to-create disabled.")

    @vc.command(name="lock")
    async def lock(self, interaction: discord.Interaction) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, connect=False)
            await send_ok(interaction, "Locked.")

    @vc.command(name="unlock")
    async def unlock(self, interaction: discord.Interaction) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, connect=True)
            await send_ok(interaction, "Unlocked.")

    @vc.command(name="hide")
    async def hide(self, interaction: discord.Interaction) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, view_channel=False)
            await send_ok(interaction, "Hidden.")

    @vc.command(name="reveal")
    async def reveal(self, interaction: discord.Interaction) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, view_channel=True)
            await send_ok(interaction, "Revealed.")

    @vc.command(name="rename")
    async def rename(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 90]) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.edit(name=name)
            await send_ok(interaction, f"Renamed to `{name}`")

    @vc.command(name="limit")
    async def limit(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.edit(user_limit=limit)
            await send_ok(interaction, f"Limit set to {limit}")

    @vc.command(name="claim")
    async def claim(self, interaction: discord.Interaction) -> None:
        if not interaction.user.voice or not isinstance(interaction.user.voice.channel, discord.VoiceChannel):
            return await send_ok(interaction, "Join a temp VC first.")
        channel = interaction.user.voice.channel
        owner_id = await temp_owner(channel.id)
        if not owner_id:
            return await send_ok(interaction, "Not a temporary voice channel.")
        owner = interaction.guild.get_member(owner_id)
        if owner and owner in channel.members:
            return await send_ok(interaction, "Owner is still here.")
        with db() as con:
            con.execute("UPDATE temp_voice SET owner_id = ? WHERE channel_id = ?", (interaction.user.id, channel.id))
        await channel.set_permissions(interaction.user, manage_channels=True, connect=True, view_channel=True)
        await send_ok(interaction, "You now own this channel.")

    @vc.command(name="godmode")
    @app_commands.checks.has_permissions(administrator=True)
    async def godmode(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        member = member or interaction.user
        with db() as con:
            con.execute("INSERT OR REPLACE INTO vc_godmode (guild_id, user_id, enabled_by, created_at) VALUES (?, ?, ?, ?)",
                        (interaction.guild_id, member.id, interaction.user.id, int(time.time())))
        await send_ok(interaction, f"God mode enabled for {member.mention}")

    @vc.command(name="godmodeoff")
    @app_commands.checks.has_permissions(administrator=True)
    async def godmodeoff(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        member = member or interaction.user
        with db() as con:
            cur = con.execute("DELETE FROM vc_godmode WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, member.id))
        await send_ok(interaction, f"God mode removed from {member.mention}." if cur.rowcount else "They didn't have god mode.")


    @vc.command(name="permit", description="Allow a member into your temp VC")
    async def permit(self, interaction: discord.Interaction, member: discord.Member) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(member, connect=True, view_channel=True)
            await send_ok(interaction, f"Permitted {member.mention}")

    @vc.command(name="reject", description="Block a member from your temp VC")
    async def reject(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if await vc_godmode_enabled(interaction.guild_id, member.id):
            return await send_ok(interaction, f"{member.mention} has VC god mode.")
        ch = await require_temp_owner(interaction)
        if ch:
            await ch.set_permissions(member, connect=False, view_channel=False)
            if member.voice and member.voice.channel == ch:
                await member.move_to(None)
            await send_purchase_dm(member)
            await send_ok(interaction, f"Rejected {member.mention}")

    @vc.command(name="transfer", description="Transfer ownership of your temp VC")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if await vc_godmode_enabled(interaction.guild_id, member.id) and member.id != interaction.user.id:
            return await send_ok(interaction, f"{member.mention} has VC god mode.")
        ch = await require_temp_owner(interaction)
        if ch:
            with db() as con:
                con.execute("UPDATE temp_voice SET owner_id = ? WHERE channel_id = ?", (member.id, ch.id))
            await ch.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
            await send_ok(interaction, f"Ownership transferred to {member.mention}")

    @vc.command(name="bitrate", description="Set bitrate of your temp VC")
    async def bitrate(self, interaction: discord.Interaction, kbps: app_commands.Range[int, 8, 384]) -> None:
        ch = await require_temp_owner(interaction)
        if ch:
            bitrate = min(kbps * 1000, interaction.guild.bitrate_limit)
            await ch.edit(bitrate=bitrate)
            await send_ok(interaction, f"Bitrate set to `{bitrate // 1000}kbps`")


# ====================== MUSIC ======================

YDL_OPTIONS = {"format": "bestaudio/best", "quiet": True, "no_warnings": True, "default_search": "ytsearch", "extract_flat": "in_playlist", "ignoreerrors": True, "noplaylist": False}
FFMPEG_OPTIONS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5", "options": "-vn"}

@dataclass
class Track:
    title: str
    webpage_url: str
    requester_id: int
    duration: Optional[int] = None

class GuildMusic:
    def __init__(self):
        self.queue: deque[Track] = deque()
        self.history: deque[Track] = deque(maxlen=25)
        self.current: Optional[Track] = None
        self.loop_track = False
        self.text_channel_id: Optional[int] = None

music_states: dict[int, GuildMusic] = defaultdict(GuildMusic)

async def ytdl_extract(query: str, max_items: int = 25) -> list[Track]:
    def run():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
        if not info:
            return []
        entries = [e for e in info.get("entries", [info]) if e][:max_items]
        return [Track(title=e.get("title") or "Unknown", webpage_url=e.get("webpage_url") or e.get("url"), requester_id=0, duration=e.get("duration")) for e in entries if e.get("webpage_url") or e.get("url")]
    return await asyncio.to_thread(run)

async def stream_url(track: Track) -> str:
    def run():
        with yt_dlp.YoutubeDL({**YDL_OPTIONS, "extract_flat": False, "noplaylist": True}) as ydl:
            return ydl.extract_info(track.webpage_url, download=False)["url"]
    return await asyncio.to_thread(run)

async def maybe_start_next(guild: discord.Guild) -> None:
    state = music_states[guild.id]
    voice = guild.voice_client
    if not voice or voice.is_playing() or voice.is_paused():
        return
    if state.loop_track and state.current:
        next_track = state.current
    elif state.queue:
        next_track = state.queue.popleft()
        if state.current:
            state.history.append(state.current)
        state.current = next_track
    else:
        state.current = None
        return
    try:
        url = await stream_url(next_track)
    except:
        await maybe_start_next(guild)
        return
    def after(_):
        asyncio.run_coroutine_threadsafe(maybe_start_next(guild), bot.loop)
    voice.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS), after=after)
    ch = bot.get_channel(state.text_channel_id) if state.text_channel_id else None
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(f"Now playing: **{next_track.title}**")
        except:
            pass

async def connect_for_music(interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
    if not interaction.user.voice or not interaction.user.voice.channel:
        await send_ok(interaction, "Join a voice channel first.")
        return None
    channel = interaction.user.voice.channel
    existing = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if existing:
        if existing.channel != channel:
            await existing.move_to(channel)
        return existing
    return await channel.connect()


class Music(commands.Cog):
    music = app_commands.Group(name="music", description="Music")

    @music.command(name="play")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        voice = await connect_for_music(interaction)
        if not voice:
            return
        tracks = await ytdl_extract(query)
        if not tracks:
            return await interaction.followup.send("No tracks found.")
        state = music_states[interaction.guild_id]
        state.text_channel_id = interaction.channel_id
        for t in tracks:
            t.requester_id = interaction.user.id
            state.queue.append(t)
        await interaction.followup.send(f"Added **{len(tracks)}** track(s).")
        await maybe_start_next(interaction.guild)

    @music.command(name="skip")
    async def skip(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.stop()
            await send_ok(interaction, "Skipped.")
        else:
            await send_ok(interaction, "Nothing playing.")

    @music.command(name="stop")
    async def stop(self, interaction: discord.Interaction) -> None:
        state = music_states[interaction.guild_id]
        state.queue.clear()
        state.current = None
        voice = interaction.guild.voice_client
        if voice:
            voice.stop()
            await voice.disconnect()
        await send_ok(interaction, "Stopped.")

    @music.command(name="queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        state = music_states[interaction.guild_id]
        lines = []
        if state.current:
            lines.append(f"**Now:** {state.current.title}")
        for i, t in enumerate(list(state.queue)[:10], 1):
            lines.append(f"{i}. {t.title}")
        await send_ok(interaction, "\n".join(lines) if lines else "Queue empty.", ephemeral=False)

    @music.command(name="pause")
    async def pause(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await send_ok(interaction, "Paused.")
        else:
            await send_ok(interaction, "Nothing playing.")

    @music.command(name="resume")
    async def resume(self, interaction: discord.Interaction) -> None:
        voice = interaction.guild.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await send_ok(interaction, "Resumed.")
        else:
            await send_ok(interaction, "Nothing paused.")

    @music.command(name="nowplaying")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        cur = music_states[interaction.guild_id].current
        await send_ok(interaction, f"**Now playing:** {cur.title}" if cur else "Nothing playing.", ephemeral=False)

    @music.command(name="loop")
    async def loop(self, interaction: discord.Interaction) -> None:
        state = music_states[interaction.guild_id]
        state.loop_track = not state.loop_track
        await send_ok(interaction, f"Loop: `{state.loop_track}`")


    @music.command(name="back", description="Play the previous song again")
    async def back(self, interaction: discord.Interaction) -> None:
        state = music_states[interaction.guild_id]
        if not state.history:
            return await send_ok(interaction, "No previous track.")
        previous = state.history.pop()
        if state.current:
            state.queue.appendleft(state.current)
        state.current = None
        state.queue.appendleft(previous)
        voice = interaction.guild.voice_client
        if voice:
            voice.stop()
        await maybe_start_next(interaction.guild)
        await send_ok(interaction, "Going back.")

    @music.command(name="remove", description="Remove a song from the queue by number")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]) -> None:
        state = music_states[interaction.guild_id]
        if position > len(state.queue):
            return await send_ok(interaction, "That queue position does not exist.")
        track = list(state.queue)[position - 1]
        del state.queue[position - 1]
        await send_ok(interaction, f"Removed **{track.title}**.")


# ====================== START ======================


class Utility(commands.Cog):
    @app_commands.command(name="serverinfo", description="Show server information")
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        embed = discord.Embed(title=g.name, color=discord.Color.blurple())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=str(g.owner), inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Created", value=g.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Boost Level", value=str(g.premium_tier), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show user information")
    async def userinfo(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        member = member or interaction.user
        embed = discord.Embed(title=str(member), color=member.color or discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "?", inline=True)
        embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
        roles = [r.mention for r in member.roles if r != interaction.guild.default_role][:15]
        embed.add_field(name="Roles", value=", ".join(roles) if roles else "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a user's avatar")
    async def avatar(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        member = member or interaction.user
        embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Show bot information")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="Bot Info", color=discord.Color.green())
        embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{round(bot.latency*1000)}ms", inline=True)
        embed.add_field(name="Prefix", value=f"`{get_config().get('prefix', '!')}`", inline=True)
        embed.add_field(name="Owners", value=str(len(get_config().get('owners', []))), inline=True)
        await interaction.response.send_message(embed=embed)


async def add_cogs() -> None:
    await bot.add_cog(General())
    await bot.add_cog(Moderation())
    await bot.add_cog(AntiNuke())
    await bot.add_cog(Levels())
    await bot.add_cog(Reminders())
    await bot.add_cog(Giveaways())
    await bot.add_cog(ServerSetup())
    await bot.add_cog(Tickets())
    await bot.add_cog(ReactionRoles())
    await bot.add_cog(VoiceMaster())
    await bot.add_cog(Music())
    await bot.add_cog(Utility())


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await send_ok(interaction, "You don't have permission for that.")
    elif isinstance(error, app_commands.BotMissingPermissions):
        await send_ok(interaction, "I am missing permissions.")
    else:
        await send_ok(interaction, f"Error: `{error}`")


async def main() -> None:
    if not TOKEN:
        raise SystemExit("Add your bot token to the .env file (DISCORD_TOKEN=...)")
    init_db()
    async with bot:
        await add_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
