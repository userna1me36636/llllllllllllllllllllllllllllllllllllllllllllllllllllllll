from __future__ import annotations

import html
import json
from typing import Any
import datetime as dt

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
    .brand { color:#ffd8e2; font-size:13px; margin-top:6px; }
    .stats { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:8px; margin-top:10px; }
    .stat { border:1px solid rgba(255,255,255,.14); border-radius:8px; padding:10px; background:rgba(255,255,255,.06); }
    .stat b { display:block; font-size:22px; }
    .stat span { color:var(--muted); font-size:12px; }
    textarea { width:100%; min-height:92px; resize:vertical; border:1px solid rgba(255,255,255,.2); background:rgba(255,255,255,.08); color:var(--text); border-radius:8px; padding:11px 12px; outline:none; font:inherit; }
    .wide { grid-column:1 / -1; }
    @media (max-width: 820px) { .grid { grid-template-columns:1fr; } header { display:block; } }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>AinBot Control</h1>
        <p>Pick a server, search what you need, and control the bot from one private dashboard.</p>
        <div class="brand">Bot owner: <b>jailer / meek</b></div>
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
        <div class="card">
          <h2>Bot Voice</h2>
          <label>Voice channel</label>
          <select id="voiceChannels"></select>
          <div class="row"><button onclick="joinVoice()">Join VC</button><button onclick="leaveVoice()">Leave VC</button></div>
        </div>
        <div class="card">
          <h2>Bot Chat</h2>
          <label>Text channel</label>
          <select id="textChannels"></select>
          <label>Message as bot</label>
          <textarea id="botMessage" maxlength="1900" placeholder="Type what the bot should send..."></textarea>
          <button onclick="sendBotMessage()">Send Message</button>
        </div>
        <p class="status" id="status"></p>
      </section>
      <main class="panel">
        <h2>Ask What You Need</h2>
        <div class="row"><input id="query" placeholder="example: stop raids, make a jtc, play music, lock vc"><button onclick="search()">Search</button></div>
        <div id="summary" class="card"></div>
        <div class="card">
          <h2>Server Control</h2>
          <div class="row">
            <div><label>Member</label><select id="members"></select></div>
            <div><label>Role</label><select id="roles"></select></div>
          </div>
          <div class="row">
            <button onclick="roleAction('add')">Add Role</button>
            <button onclick="roleAction('remove')">Remove Role</button>
            <button onclick="timeoutMember()">Timeout</button>
            <button onclick="untimeoutMember()">Untimeout</button>
          </div>
          <div class="row">
            <button onclick="moveMember()">Move To VC</button>
            <button onclick="disconnectMember()">Disconnect VC</button>
            <button onclick="kickMember()">Kick</button>
            <button onclick="banMember()">Ban</button>
          </div>
        </div>
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
  $('summary').innerHTML = `<h2>${data.name}</h2><span class="pill">${data.members} members</span><span class="pill">${data.channels} channels</span><span class="pill">${data.roles} roles</span><span class="pill">prefix ${data.prefix}</span><span class="pill">bot ${data.bot_name}</span><div class="stats"><div class="stat"><b>${data.slash_commands}</b><span>slash commands</span></div><div class="stat"><b>${data.prefix_commands}</b><span>prefix commands</span></div><div class="stat"><b>${data.total_commands}</b><span>total commands</span></div><div class="stat"><b>${data.voice_channels.length}</b><span>voice channels</span></div></div>`;
  $('voiceChannels').innerHTML = data.voice_channels.map(v=>`<option value="${v.id}">${v.name}</option>`).join('');
  $('textChannels').innerHTML = data.text_channels.map(c=>`<option value="${c.id}">#${c.name}</option>`).join('');
  $('members').innerHTML = data.members_list.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
  $('roles').innerHTML = data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
}
function renderCommands(commands){
  $('results').innerHTML = commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join('') || '<p>No commands found.</p>';
}
async function loadCommands(){ const data = await api('/api/guild/' + guild() + '/commands'); renderCommands(data.commands); }
async function search(){ const data = await api('/api/guild/' + guild() + '/search?q=' + encodeURIComponent($('query').value)); renderCommands(data.commands); }
async function savePrefix(){ await api('/api/guild/' + guild() + '/prefix', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({prefix:$('prefix').value})}); setStatus('Prefix saved.'); loadSummary(); }
async function saveTheme(){ await api('/api/guild/' + guild() + '/theme', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({color:$('color').value})}); setStatus('Theme saved.'); }
async function feature(enabled){ await api('/api/guild/' + guild() + '/feature', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({feature:$('feature').value, enabled})}); setStatus('Feature updated.'); }
async function joinVoice(){ await api('/api/guild/' + guild() + '/voice/join', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({channel_id:$('voiceChannels').value})}); setStatus('Bot joined the VC.'); }
async function leaveVoice(){ await api('/api/guild/' + guild() + '/voice/leave', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({})}); setStatus('Bot left the VC.'); }
async function sendBotMessage(){ await api('/api/guild/' + guild() + '/message', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({channel_id:$('textChannels').value, message:$('botMessage').value})}); setStatus('Message sent as bot.'); $('botMessage').value=''; }
async function roleAction(action){ await api('/api/guild/' + guild() + '/member/role', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, role_id:$('roles').value, action})}); setStatus('Role updated.'); }
async function timeoutMember(){ await api('/api/guild/' + guild() + '/member/timeout', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, minutes:10})}); setStatus('Member timed out for 10 minutes.'); }
async function untimeoutMember(){ await api('/api/guild/' + guild() + '/member/untimeout', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Timeout removed.'); }
async function moveMember(){ await api('/api/guild/' + guild() + '/member/move', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, channel_id:$('voiceChannels').value})}); setStatus('Member moved.'); }
async function disconnectMember(){ await api('/api/guild/' + guild() + '/member/disconnect', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member disconnected.'); }
async function kickMember(){ if(confirm('Kick this member?')){ await api('/api/guild/' + guild() + '/member/kick', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member kicked.'); } }
async function banMember(){ if(confirm('Ban this member?')){ await api('/api/guild/' + guild() + '/member/ban', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member banned.'); } }
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

    def command_counts(self) -> dict[str, int]:
        slash = len(list(self.bot.tree.walk_commands()))
        prefix = len([command for command in self.bot.walk_commands() if not command.hidden])
        return {"slash_commands": slash, "prefix_commands": prefix, "total_commands": slash + prefix}

    def get_member_or_404(self, guild: discord.Guild, member_id: Any) -> discord.Member:
        member = guild.get_member(int(member_id or 0))
        if member is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "Member not found or not cached."}), content_type="application/json")
        return member

    def require_manageable_member(self, guild: discord.Guild, member: discord.Member) -> None:
        me = guild.me
        if me is None:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Bot member was not found."}), content_type="application/json")
        if member.top_role >= me.top_role and member != guild.owner:
            raise web.HTTPForbidden(text=json.dumps({"error": "Bot role is not high enough to manage that member."}), content_type="application/json")

    def get_role_or_404(self, guild: discord.Guild, role_id: Any) -> discord.Role:
        role = guild.get_role(int(role_id or 0))
        if role is None:
            raise web.HTTPNotFound(text=json.dumps({"error": "Role not found."}), content_type="application/json")
        return role

    def require_manageable_role(self, guild: discord.Guild, role: discord.Role) -> None:
        me = guild.me
        if me is None or role >= me.top_role:
            raise web.HTTPForbidden(text=json.dumps({"error": "Bot role is not high enough to manage that role."}), content_type="application/json")

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
        voice_channels = [{"id": str(channel.id), "name": channel.name} for channel in guild.voice_channels]
        text_channels = [{"id": str(channel.id), "name": channel.name} for channel in guild.text_channels]
        members = sorted(guild.members, key=lambda member: member.display_name.lower())[:250]
        roles = [role for role in sorted(guild.roles, key=lambda role: role.position, reverse=True) if not role.is_default() and not role.managed]
        payload = {
            "id": str(guild.id),
            "name": guild.name,
            "bot_name": str(guild.me.display_name if guild.me else self.bot.user),
            "members": guild.member_count or 0,
            "channels": len(guild.channels),
            "roles": len(guild.roles),
            "prefix": settings.get("prefix", self.bot.settings.default_prefix),
            "voice_channels": voice_channels,
            "text_channels": text_channels,
            "members_list": [{"id": str(member.id), "name": member.display_name} for member in members],
            "role_list": [{"id": str(role.id), "name": role.name} for role in roles[:250]],
        }
        payload.update(self.command_counts())
        return web.json_response(payload)

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

    async def join_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        if not isinstance(channel, discord.VoiceChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid voice channel."}), content_type="application/json")
        current = guild.voice_client
        if current and current.is_connected():
            await current.move_to(channel)
        else:
            await channel.connect(self_deaf=True)
        return web.json_response({"ok": True, "channel": channel.name})

    async def leave_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        current = guild.voice_client
        if current and current.is_connected():
            await current.disconnect(force=True)
        return web.json_response({"ok": True})

    async def send_message(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        message = str(body.get("message", "")).strip()[:1900]
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid text channel."}), content_type="application/json")
        if not message:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Message cannot be empty."}), content_type="application/json")
        await channel.send(message)
        return web.json_response({"ok": True})

    async def member_role(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        role = self.get_role_or_404(guild, body.get("role_id"))
        self.require_manageable_role(guild, role)
        action = str(body.get("action", "add")).lower()
        if action == "remove":
            await member.remove_roles(role, reason="Dashboard role remove")
        else:
            await member.add_roles(role, reason="Dashboard role add")
        return web.json_response({"ok": True})

    async def timeout_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        self.require_manageable_member(guild, member)
        minutes = max(1, min(int(body.get("minutes", 10) or 10), 10080))
        await member.timeout(dt.timedelta(minutes=minutes), reason="Dashboard timeout")
        return web.json_response({"ok": True})

    async def untimeout_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        self.require_manageable_member(guild, member)
        await member.timeout(None, reason="Dashboard untimeout")
        return web.json_response({"ok": True})

    async def move_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        if not isinstance(channel, discord.VoiceChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid voice channel."}), content_type="application/json")
        await member.move_to(channel, reason="Dashboard voice move")
        return web.json_response({"ok": True})

    async def disconnect_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        await member.move_to(None, reason="Dashboard voice disconnect")
        return web.json_response({"ok": True})

    async def kick_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        self.require_manageable_member(guild, member)
        await member.kick(reason="Dashboard kick")
        return web.json_response({"ok": True})

    async def ban_member(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        self.require_manageable_member(guild, member)
        await member.ban(reason="Dashboard ban", delete_message_days=0)
        return web.json_response({"ok": True})


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
    app.router.add_post("/api/guild/{guild_id}/voice/join", dashboard.join_voice)
    app.router.add_post("/api/guild/{guild_id}/voice/leave", dashboard.leave_voice)
    app.router.add_post("/api/guild/{guild_id}/message", dashboard.send_message)
    app.router.add_post("/api/guild/{guild_id}/member/role", dashboard.member_role)
    app.router.add_post("/api/guild/{guild_id}/member/timeout", dashboard.timeout_member)
    app.router.add_post("/api/guild/{guild_id}/member/untimeout", dashboard.untimeout_member)
    app.router.add_post("/api/guild/{guild_id}/member/move", dashboard.move_member)
    app.router.add_post("/api/guild/{guild_id}/member/disconnect", dashboard.disconnect_member)
    app.router.add_post("/api/guild/{guild_id}/member/kick", dashboard.kick_member)
    app.router.add_post("/api/guild/{guild_id}/member/ban", dashboard.ban_member)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(getattr(bot.settings, "dashboard_port", 8080)))
    await site.start()
    bot.log.info("Dashboard listening on port %s", getattr(bot.settings, "dashboard_port", 8080))
