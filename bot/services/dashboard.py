from __future__ import annotations

import html
import json
from typing import Any

import discord
from aiohttp import web
from discord.ext import commands


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AinBot Control</title>
  <style>
    :root { color-scheme: dark; --bg:#07070b; --panel:rgba(255,255,255,.075); --line:rgba(255,255,255,.22); --red:rgba(178,24,44,.42); --text:#f7f2f5; --muted:#b8aeb8; --hot:#ff4f73; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:radial-gradient(circle at top left, rgba(255,79,115,.25), transparent 28rem), linear-gradient(135deg,#07070b,#171017 65%,#240611); color:var(--text); font-family:Inter,Segoe UI,Arial,sans-serif; }
    .wrap { width:min(1180px, calc(100% - 28px)); margin:0 auto; padding:28px 0; }
    header { display:flex; justify-content:space-between; align-items:center; gap:18px; margin-bottom:18px; }
    h1 { margin:0; font-size:clamp(30px,5vw,58px); letter-spacing:0; }
    h2 { margin:0 0 12px; font-size:20px; }
    p { color:var(--muted); line-height:1.5; }
    .grid { display:grid; grid-template-columns: 360px 1fr; gap:16px; align-items:start; }
    .panel { border:1px solid var(--line); background:linear-gradient(145deg,var(--red),rgba(255,255,255,.055)); backdrop-filter:blur(16px); border-radius:8px; padding:16px; box-shadow:0 20px 80px rgba(0,0,0,.35); }
    .card { border:1px solid rgba(255,255,255,.14); background:rgba(0,0,0,.22); border-radius:8px; padding:12px; margin-top:10px; }
    label { display:block; color:var(--muted); font-size:12px; margin:12px 0 6px; }
    input, select { width:100%; border:1px solid rgba(255,255,255,.2); background:rgba(255,255,255,.08); color:var(--text); border-radius:8px; padding:11px 12px; outline:none; }
    button { border:1px solid rgba(255,255,255,.28); background:rgba(255,255,255,.11); color:var(--text); border-radius:8px; padding:10px 12px; cursor:pointer; }
    button:hover { border-color:var(--hot); }
    .row { display:flex; gap:8px; }
    .row > * { flex:1; }
    .pill { display:inline-flex; border:1px solid rgba(255,255,255,.18); border-radius:999px; padding:6px 9px; margin:3px; color:#fff; background:rgba(255,255,255,.08); font-size:12px; }
    .cmd { display:grid; grid-template-columns: minmax(130px, 220px) 1fr; gap:10px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,.11); }
    .cmd:last-child { border-bottom:0; }
    .cmd b { color:#fff; }
    .cmd span { color:var(--muted); }
    .status { min-height:22px; color:#ffd0dc; font-size:13px; }
    @media (max-width: 820px) { .grid { grid-template-columns:1fr; } header { display:block; } }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>AinBot Control</h1>
        <p>Pick a server, search what you need, and control the bot from one private dashboard.</p>
      </div>
      <button onclick="loadGuilds()">Refresh</button>
    </header>
    <div class="grid">
      <section class="panel">
        <h2>Connect</h2>
        <label>Dashboard token</label>
        <input id="token" placeholder="DASHBOARD_TOKEN" type="password">
        <label>Server</label>
        <select id="guilds" onchange="loadSummary()"></select>
        <div class="row">
          <button onclick="loadGuilds()">Load Servers</button>
          <button onclick="loadCommands()">Commands</button>
        </div>
        <div class="card">
          <h2>Quick Controls</h2>
          <label>Prefix</label>
          <div class="row"><input id="prefix" placeholder="," maxlength="12"><button onclick="savePrefix()">Save</button></div>
          <label>Theme color</label>
          <div class="row"><input id="color" placeholder="#b2182c"><button onclick="saveTheme()">Save</button></div>
          <label>Feature</label>
          <div class="row"><input id="feature" placeholder="music"><button onclick="feature(true)">On</button><button onclick="feature(false)">Off</button></div>
        </div>
        <p class="status" id="status"></p>
      </section>
      <main class="panel">
        <h2>Ask What You Need</h2>
        <div class="row"><input id="query" placeholder="example: stop raids, make a jtc, play music, lock vc"><button onclick="search()">Search</button></div>
        <div id="summary" class="card"></div>
        <div id="results" class="card"></div>
      </main>
    </div>
  </div>
<script>
const $ = id => document.getElementById(id);
$('token').value = localStorage.ainToken || '';
function token(){ localStorage.ainToken = $('token').value; return encodeURIComponent($('token').value); }
function guild(){ return $('guilds').value; }
function setStatus(t){ $('status').textContent = t; }
async function api(path, opts={}) {
  const sep = path.includes('?') ? '&' : '?';
  const res = await fetch(path + sep + 'token=' + token(), opts);
  const data = await res.json().catch(()=>({error:'Bad response'}));
  if (!res.ok) throw new Error(data.error || 'Request failed');
  return data;
}
async function loadGuilds(){
  try {
    const data = await api('/api/guilds');
    $('guilds').innerHTML = data.guilds.map(g=>`<option value="${g.id}">${g.name} (${g.id})</option>`).join('');
    setStatus('Servers loaded.');
    await loadSummary();
  } catch(e){ setStatus(e.message); }
}
async function loadSummary(){
  if(!guild()) return;
  const data = await api('/api/guild/' + guild() + '/summary');
  $('summary').innerHTML = `<h2>${data.name}</h2><span class="pill">${data.members} members</span><span class="pill">${data.channels} channels</span><span class="pill">${data.roles} roles</span><span class="pill">prefix ${data.prefix}</span>`;
}
function renderCommands(commands){
  $('results').innerHTML = commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join('') || '<p>No commands found.</p>';
}
async function loadCommands(){ const data = await api('/api/guild/' + guild() + '/commands'); renderCommands(data.commands); }
async function search(){ const data = await api('/api/guild/' + guild() + '/search?q=' + encodeURIComponent($('query').value)); renderCommands(data.commands); }
async function savePrefix(){ await api('/api/guild/' + guild() + '/prefix', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({prefix:$('prefix').value})}); setStatus('Prefix saved.'); loadSummary(); }
async function saveTheme(){ await api('/api/guild/' + guild() + '/theme', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({color:$('color').value})}); setStatus('Theme saved.'); }
async function feature(enabled){ await api('/api/guild/' + guild() + '/feature', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({feature:$('feature').value, enabled})}); setStatus('Feature updated.'); }
</script>
</body>
</html>"""


class Dashboard:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def require_token(self, request: web.Request) -> None:
        expected = getattr(self.bot.settings, "dashboard_token", None)
        provided = request.query.get("token") or request.headers.get("x-dashboard-token")
        if not expected:
            raise web.HTTPUnauthorized(text=json.dumps({"error": "Set DASHBOARD_TOKEN in Railway Variables first."}), content_type="application/json")
        if provided != expected:
            raise web.HTTPForbidden(text=json.dumps({"error": "Wrong dashboard token."}), content_type="application/json")

    def guild_or_404(self, guild_id: str) -> discord.Guild:
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "That server is not connected to this bot."}), content_type="application/json")
        return guild

    def command_list(self) -> list[dict[str, str]]:
        commands_out: list[dict[str, str]] = []
        for command in self.bot.tree.walk_commands():
            commands_out.append({"name": "/" + command.qualified_name, "description": getattr(command, "description", "") or ""})
        for command in self.bot.walk_commands():
            if command.hidden:
                continue
            commands_out.append({"name": self.bot.settings.default_prefix + command.qualified_name, "description": command.help or command.short_doc or ""})
        return sorted(commands_out, key=lambda item: item["name"])

    async def index(self, _: web.Request) -> web.Response:
        return web.Response(text=dashboard_html(), content_type="text/html")

    async def guilds(self, request: web.Request) -> web.Response:
        self.require_token(request)
        data = [{"id": str(guild.id), "name": guild.name, "members": guild.member_count or 0} for guild in self.bot.guilds]
        return web.json_response({"guilds": data})

    async def summary(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        return web.json_response({
            "id": str(guild.id),
            "name": guild.name,
            "members": guild.member_count or 0,
            "channels": len(guild.channels),
            "roles": len(guild.roles),
            "prefix": settings.get("prefix", self.bot.settings.default_prefix),
        })

    async def commands(self, request: web.Request) -> web.Response:
        self.require_token(request)
        self.guild_or_404(request.match_info["guild_id"])
        return web.json_response({"commands": self.command_list()})

    async def search(self, request: web.Request) -> web.Response:
        self.require_token(request)
        self.guild_or_404(request.match_info["guild_id"])
        query = (request.query.get("q") or "").lower()
        words = [word for word in query.replace(",", " ").split() if len(word) > 1]
        commands_out = []
        for item in self.command_list():
            haystack = f"{item['name']} {item['description']}".lower()
            score = sum(1 for word in words if word in haystack)
            if score or not words:
                enriched = dict(item)
                enriched["score"] = score
                commands_out.append(enriched)
        commands_out.sort(key=lambda item: (-item["score"], item["name"]))
        return web.json_response({"commands": commands_out[:30]})

    async def set_prefix(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        prefix = str(body.get("prefix", self.bot.settings.default_prefix))[:12]
        await self.bot.db.set_prefix(guild.id, prefix, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "prefix": prefix})

    async def set_theme(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        raw = str(body.get("color", "#b2182c")).strip().lstrip("#")
        color = int(raw, 16) if len(raw) == 6 else 0xB2182C
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        theme["color"] = color
        await self.bot.db.set_settings_value(guild.id, "theme", theme, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "color": color})

    async def set_feature(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        feature = html.escape(str(body.get("feature", "")).strip().lower())[:40]
        enabled = bool(body.get("enabled", True))
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        flags = settings.get("feature_flags", {})
        flags[feature] = enabled
        await self.bot.db.set_settings_value(guild.id, "feature_flags", flags, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "feature": feature, "enabled": enabled})


async def start_dashboard(bot: commands.Bot) -> None:
    dashboard = Dashboard(bot)
    app = web.Application()
    app.router.add_get("/", dashboard.index)
    app.router.add_get("/api/guilds", dashboard.guilds)
    app.router.add_get("/api/guild/{guild_id}/summary", dashboard.summary)
    app.router.add_get("/api/guild/{guild_id}/commands", dashboard.commands)
    app.router.add_get("/api/guild/{guild_id}/search", dashboard.search)
    app.router.add_post("/api/guild/{guild_id}/prefix", dashboard.set_prefix)
    app.router.add_post("/api/guild/{guild_id}/theme", dashboard.set_theme)
    app.router.add_post("/api/guild/{guild_id}/feature", dashboard.set_feature)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(getattr(bot.settings, "dashboard_port", 8080)))
    await site.start()
    bot.log.info("Dashboard listening on port %s", getattr(bot.settings, "dashboard_port", 8080))
