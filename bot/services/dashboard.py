from __future__ import annotations

import html
import asyncio
import json
import os
import tempfile
import time
from typing import Any
import datetime as dt
from pathlib import Path

import discord
try:
    import edge_tts
except ImportError:  # Keep the whole bot online when an optional TTS install is missing.
    edge_tts = None
from aiohttp import ClientSession, web
from discord.ext import commands

from bot.cogs.server_backup import make_code
from bot.core.utils import is_multicolor_theme, theme_color_from_data
from bot.services.music import ffmpeg_executable


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AinBot Control</title>
  <style>
    :root { color-scheme: dark; --bg:#07070b; --panel:rgba(255,255,255,.075); --line:rgba(255,255,255,.22); --red:rgba(178,24,44,.42); --text:#f7f2f5; --muted:#d7ccd7; --hot:#ff4f73; --a:#ff3864; --b:#8f5cff; --c:#20d3ff; --d:#42ff9e; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:linear-gradient(125deg,#09070d,#1b0820,#071827,#10110a,#220811); background-size:520% 520%; color:var(--text); font-family:Inter,Segoe UI,Arial,sans-serif; animation:auroraShift 28s ease-in-out infinite; position:relative; overflow-x:hidden; }
    body::before { content:""; position:fixed; inset:-18%; pointer-events:none; background:radial-gradient(circle at 15% 20%, rgba(255,56,100,.42), transparent 28%), radial-gradient(circle at 78% 12%, rgba(143,92,255,.38), transparent 30%), radial-gradient(circle at 88% 72%, rgba(32,211,255,.3), transparent 28%), radial-gradient(circle at 18% 84%, rgba(66,255,158,.2), transparent 30%); filter:blur(20px); opacity:.75; animation:glowDrift 34s ease-in-out infinite alternate; }
    body::after { content:""; position:fixed; inset:0; pointer-events:none; background:linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px); background-size:42px 42px; mask-image:linear-gradient(to bottom, rgba(0,0,0,.72), transparent 85%); }
    @keyframes auroraShift { 0%{background-position:0% 50%;} 33%{background-position:80% 20%;} 66%{background-position:20% 90%;} 100%{background-position:0% 50%;} }
    @keyframes glowDrift { 0%{transform:translate3d(-2%, -1%, 0) rotate(0deg) scale(1);} 50%{transform:translate3d(2%, 2%, 0) rotate(8deg) scale(1.05);} 100%{transform:translate3d(0, -2%, 0) rotate(-6deg) scale(1.02);} }
    @keyframes borderPulse { 0%,100%{border-color:rgba(255,255,255,.2); box-shadow:0 20px 80px rgba(0,0,0,.38), inset 0 1px 0 rgba(255,255,255,.14);} 50%{border-color:rgba(143,92,255,.52); box-shadow:0 20px 90px rgba(32,211,255,.14), inset 0 1px 0 rgba(255,255,255,.22);} }
    .wrap { width:min(1180px, calc(100% - 28px)); margin:0 auto; padding:28px 0; }
    header { display:flex; justify-content:space-between; align-items:center; gap:18px; margin-bottom:18px; }
    h1 { margin:0; font-size:clamp(30px,5vw,58px); letter-spacing:0; }
    h2 { margin:0 0 12px; font-size:20px; }
    p { color:var(--muted); line-height:1.5; }
    .grid { display:grid; grid-template-columns: 360px 1fr; gap:16px; align-items:start; }
    .panel { border:1px solid var(--line); background:linear-gradient(145deg,rgba(255,56,100,.18),rgba(143,92,255,.13),rgba(32,211,255,.08),rgba(255,255,255,.05)); backdrop-filter:blur(18px) saturate(140%); border-radius:8px; padding:16px; animation:borderPulse 12s ease-in-out infinite; position:relative; z-index:1; }
    .card { border:1px solid rgba(255,255,255,.16); background:linear-gradient(145deg,rgba(0,0,0,.38),rgba(255,255,255,.06)); border-radius:8px; padding:12px; margin-top:10px; box-shadow:inset 0 1px 0 rgba(255,255,255,.08); }
    label { display:block; color:var(--muted); font-size:12px; margin:12px 0 6px; }
    input, select { width:100%; border:1px solid rgba(255,255,255,.2); background:#171017; color:var(--text); border-radius:8px; padding:11px 12px; outline:none; }
    option { background:#171017; color:#f7f2f5; }
    option:checked, option:hover { background:#b2182c; color:#fff; }
    button { border:1px solid rgba(255,255,255,.28); background:linear-gradient(135deg,rgba(255,56,100,.22),rgba(143,92,255,.18),rgba(32,211,255,.13)); color:var(--text); border-radius:8px; padding:10px 12px; cursor:pointer; box-shadow:inset 0 1px 0 rgba(255,255,255,.14); }
    button:hover { border-color:var(--hot); }
    .row { display:flex; gap:8px; }
    .row > * { flex:1; }
    .pill { display:inline-flex; border:1px solid rgba(255,255,255,.18); border-radius:999px; padding:6px 9px; margin:3px; color:#fff; background:linear-gradient(135deg,rgba(255,56,100,.18),rgba(32,211,255,.12)); font-size:12px; }
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
    .tabs { display:flex; gap:8px; margin:0 0 16px; overflow-x:auto; position:relative; z-index:2; }
    .tabs button.active { border-color:var(--hot); background:linear-gradient(135deg,rgba(255,56,100,.55),rgba(143,92,255,.35)); }
    .tabpage { display:none; }
    .tabpage.active { display:grid; }
    .tts-layout { grid-template-columns:minmax(0,1fr) 320px; gap:16px; }
    .slider-line { display:grid; grid-template-columns:90px 1fr 54px; align-items:center; gap:10px; }
    .slider-line output { text-align:right; color:var(--muted); }
    .connection { display:flex; align-items:center; gap:8px; color:var(--muted); }
    .connection::before { content:""; width:10px; height:10px; border-radius:50%; background:#777; box-shadow:0 0 12px #777; }
    .connection.online::before { background:var(--d); box-shadow:0 0 14px var(--d); }
    .designer { grid-template-columns:minmax(320px, .9fr) minmax(360px, 1.1fr); gap:16px; }
    .discord-preview { background:#313338; border-radius:8px; padding:18px; min-height:360px; }
    .discord-message { display:grid; grid-template-columns:42px 1fr; gap:12px; }
    .discord-avatar { width:42px; height:42px; border-radius:50%; background:linear-gradient(135deg,var(--a),var(--b),var(--c)); }
    .discord-name { color:#f2f3f5; font-weight:700; margin-bottom:6px; }.discord-name small{color:#949ba4;font-weight:400}
    .embed-preview { border-left:4px solid var(--hot); background:#2b2d31; border-radius:4px; padding:12px 14px; max-width:560px; color:#dbdee1; }
    .embed-preview h3 { color:#f2f3f5; margin:0 0 8px; }.embed-preview p{margin:0 0 10px;color:#dbdee1}.preview-field{margin-top:9px}.preview-field b{display:block;color:#f2f3f5}.preview-field span{white-space:pre-wrap}.preview-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.preview-footer{margin-top:12px;color:#949ba4;font-size:11px}
    button.danger { border-color:rgba(255,79,115,.65); }
    /* Classic AIN layout: neutral Discord-like shell with a permanent left connection rail. */
    body { background:#0d0f0e; color:#ecebe7; animation:none; }
    body::before, body::after { display:none; }
    .wrap { width:min(1240px,calc(100% - 32px)); display:grid; grid-template-columns:280px minmax(0,1fr); gap:18px; padding:38px 0; border-top:1px solid #343733; }
    header { display:none; }
    .tabs { grid-column:2; grid-row:1; flex-wrap:wrap; overflow:visible; gap:4px 8px; margin:0; padding:12px 16px; background:#171916; border:1px solid #353832; border-bottom:0; border-radius:16px 16px 0 0; }
    .tabs button { border-color:transparent; background:transparent; color:#c9c6bf; box-shadow:none; padding:9px 12px; }
    .tabs button:hover { background:#242622; border-color:#3b3e37; }
    .tabs button.active { background:#40271f; border-color:#87513e; color:#fff; }
    .panel { background:#171916; border-color:#353832; border-radius:16px; box-shadow:0 18px 45px rgba(0,0,0,.24); animation:none; backdrop-filter:none; }
    .card { background:#1c1e1b; border-color:#383b35; border-radius:14px; box-shadow:none; }
    input, select, textarea { background:#111310; border-color:#3b3e37; border-radius:10px; }
    button { background:#282a26; border-color:#3d4039; border-radius:9px; box-shadow:none; }
    button:hover { border-color:#76513f; background:#302c27; }
    #dashboardTab.active { display:contents; }
    #dashboardTab > section { grid-column:1; grid-row:1 / span 3; }
    #dashboardTab > main { grid-column:2; grid-row:2; border-radius:0 0 16px 16px; }
    #ttsTab, #panelTab { grid-column:2; grid-row:2; border:1px solid #353832; border-top:0; padding:16px; background:#171916; border-radius:0 0 16px 16px; }
    .tabpage.active:not(#dashboardTab) { display:grid; }
    .dashboard-card.filtered-out { display:none; }
    @media (prefers-reduced-motion: reduce) { body, body::before, .panel { animation:none; } }
    @media (max-width: 820px) { .wrap{display:block;width:min(100% - 20px,680px);padding:18px 0}.tabs{border-radius:14px;margin-top:12px;border-bottom:1px solid #353832}#dashboardTab.active{display:grid}#dashboardTab > section,#dashboardTab > main,#ttsTab,#panelTab{display:block;margin-top:12px;border-radius:14px;border:1px solid #353832}.grid, .tts-layout, .designer { grid-template-columns:1fr; } .row { flex-wrap:wrap; } .slider-line { grid-template-columns:70px 1fr 46px; } .preview-cards{grid-template-columns:1fr} }
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
    <nav class="tabs" aria-label="Dashboard sections">
      <button class="active" data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Overview</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('commands',this)">All Commands</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('security',this)">Defense</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Setup Guide</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Engagement</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Member Transfer</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('economy',this)">Payments</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Promo Codes</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('overview',this)">Giveaways</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('server',this)">Live Channels</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('server',this)">Server Control</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('ai',this)">AI Assistant</button>
      <button data-tab="ttsTab" onclick="showTab('ttsTab',this)">Voice & TTS</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('music',this)">Music</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('security',this)">Security</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('economy',this)">Economy & Roles</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('server',this)">Members</button>
      <button data-tab="dashboardTab" onclick="showDashboardView('logs',this)">Logs</button>
      <button data-tab="panelTab" onclick="showTab('panelTab',this)">Panel Designer</button>
    </nav>
    <div id="dashboardTab" class="grid tabpage active">
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
          <div class="row"><input id="color" placeholder="#b2182c or fade"><button onclick="saveTheme()">Save</button></div>
          <label>Feature</label>
          <div class="row"><input id="feature" placeholder="music"><button onclick="feature(true)">On</button><button onclick="feature(false)">Off</button></div>
        </div>
        <select id="voiceChannels" hidden></select>
        <div class="card">
          <h2>Bot Chat</h2>
          <label>Text channel</label>
          <select id="textChannels"></select>
          <label>Message as bot</label>
          <textarea id="botMessage" maxlength="1900" placeholder="Type what the bot should send..."></textarea>
          <button onclick="sendBotMessage()">Send Message</button>
        </div>
        <div class="card">
          <h2>Announcement Embed</h2>
          <label>Title</label><input id="embedTitle" placeholder="Update">
          <label>Message</label><textarea id="embedText" maxlength="3500" placeholder="Clean announcement text..."></textarea>
          <button onclick="sendEmbed()">Send Embed</button>
        </div>
        <p class="status" id="status"></p>
      </section>
      <main class="panel">
        <h2>Ask What You Need</h2>
        <div class="row"><input id="query" placeholder="example: stop raids, make a jtc, play music, lock vc"><button onclick="search()">Search</button></div>
        <div id="summary" class="card"></div>
        <div class="card dashboard-card" data-section="ai">
          <h2>Command Assistant</h2>
          <label>Ask about commands</label>
          <textarea id="assistantQuestion" maxlength="900" placeholder="Example: how do I set up anti nuke, make a ticket, or play music?"></textarea>
          <button onclick="askAssistant()">Ask Assistant</button>
          <div id="assistantBox"></div>
        </div>
        <div class="card dashboard-card" data-section="server">
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
        <div class="card dashboard-card" data-section="music">
          <h2>Music Controls</h2>
          <label>Song or URL</label><input id="musicQuery" placeholder="YouTube, playlist, or search">
          <div class="row"><button onclick="music('add')">Add</button><button onclick="music('play')">Play</button><button onclick="music('pause')">Pause</button><button onclick="music('resume')">Resume</button></div>
          <div class="row"><button onclick="music('skip')">Skip</button><button onclick="music('stop')">Stop</button><button onclick="music('loop')">Loop</button><button onclick="music('shuffle')">Shuffle</button></div>
          <label>Volume</label><div class="row"><input id="musicVolume" type="number" min="1" max="200" value="70"><button onclick="music('volume')">Set Volume</button></div>
          <div id="musicBox" class="card"></div>
        </div>
        <div class="card dashboard-card" data-section="security">
          <h2>Security & Backup</h2>
          <div class="row"><button onclick="backup()">Make Backup Code</button><button onclick="antinuke(true)">Anti-Nuke On</button><button onclick="antinuke(false)">Anti-Nuke Off</button></div>
          <label>Whitelist selected member/role</label>
          <div class="row"><button onclick="antiWhitelist('member')">Whitelist Member</button><button onclick="antiWhitelist('role')">Whitelist Role</button></div>
          <p id="backupBox"></p>
        </div>
        <div class="card dashboard-card" data-section="economy">
          <h2>Economy & Roles</h2>
          <label>Coins</label><input id="coins" type="number" value="1000">
          <div class="row"><button onclick="coins('add')">Add Coins</button><button onclick="coins('take')">Take Coins</button><button onclick="coins('set')">Set Wallet</button></div>
          <h2>Shop Editor</h2>
          <label>Item key</label><input id="shopKey" placeholder="vip-pass">
          <label>Price</label><input id="shopPrice" type="number" value="2500">
          <label>Description</label><input id="shopDescription" placeholder="Gives VIP role">
          <label>Reward role optional</label><select id="shopRole"></select>
          <div class="row"><button onclick="shopSave()">Save Item</button><button onclick="shopDelete()">Delete Item</button><button onclick="shopLoad()">Show Shop</button></div>
          <div id="shopBox"></div>
          <label>Role name</label><input id="roleName" placeholder="New role name">
          <label>Role color</label><input id="roleColor" placeholder="#b2182c">
          <div class="row"><button onclick="createRole()">Create Role</button><button onclick="renameRole()">Rename Selected Role</button><button onclick="moveRoleTop()">Move Selected Role Top</button></div>
        </div>
        <div class="card dashboard-card" data-section="logs">
          <h2>Live Logs</h2>
          <button onclick="loadLogs()">Refresh Logs</button>
          <div id="logsBox"></div>
        </div>
        <div id="results" class="card dashboard-card" data-section="commands"></div>
      </main>
    </div>
    <section id="panelTab" class="tabpage designer">
      <div class="panel">
        <h2>Discord Panel Designer</h2><p>Build the full command panel layout each server sees—not just its color.</p>
        <label>Your Discord user ID</label><input id="panelActorId" inputmode="numeric" placeholder="Server owner or approved role">
        <label>Text channel</label><select id="panelChannel"></select>
        <label>Saved interfaces</label><div class="row"><select id="panelProfiles" onchange="selectPanelProfile()"><option value="">New interface</option></select><button onclick="newPanelDesign()">New</button><button class="danger" onclick="deletePanelDesign()">Delete</button></div>
        <label>Interface name</label><input id="panelName" maxlength="40" placeholder="Example: Voice Commands, Neon Shop, Simple Help">
        <div class="row"><div><label>Layout</label><select id="panelLayout"><option value="compact">Compact command list</option><option value="cards">Command cards</option><option value="minimal">Minimal panel</option></select></div><div><label>Accent</label><input id="panelColor" type="color" value="#5865f2"></div></div>
        <label>Panel title</label><input id="panelTitle" maxlength="120" value="Voice Channel Controls">
        <label>Description</label><textarea id="panelDescription" maxlength="1000">Manage your temporary voice channels with the commands below.</textarea>
        <label>Commands (one per line: command | explanation)</label><textarea id="panelFields" maxlength="3500">/vc count | View active users
/vc rename &lt;name&gt; | Rename your room
/vc lock | Lock room
/vc unlock | Unlock room
/vc permit &lt;user&gt; | Permit user
/vc reject &lt;user&gt; | Reject user
/vc limit &lt;1-100&gt; | Set room limit
/vc transfer &lt;user&gt; | Transfer ownership</textarea>
        <label>Footer</label><input id="panelFooter" maxlength="200" value="AIN Bot • Server controls">
        <label>Thumbnail URL (optional)</label><input id="panelThumbnail" placeholder="https://...">
        <div class="row"><button onclick="loadPanelDesign()">Load Selected</button><button onclick="savePanelDesign()">Save Named Design</button><button onclick="sendPanelDesign()">Send Panel</button></div>
        <p class="status" id="panelStatus"></p>
      </div>
      <div class="panel"><h2>Live Discord Preview</h2><div class="discord-preview"><div class="discord-message"><div class="discord-avatar"></div><div><div class="discord-name">AIN Bot <small>BOT · Today</small></div><div class="embed-preview" id="panelPreview"></div></div></div></div><p>Discord controls the outer font and message frame. AIN controls the title, description, fields, arrangement, accent, image, and footer.</p></div>
    </section>
    <section id="ttsTab" class="tabpage tts-layout">
      <div class="panel">
        <h2>Text to Speech</h2>
        <p>Generate audio on the bot server and play it directly in Discord—your microphone is never used.</p>
        <label for="ttsText">What should AIN Bot say? <span id="ttsCount">0</span>/500</label>
        <textarea id="ttsText" maxlength="500" placeholder="Type what the bot should say..."></textarea>
        <div class="row">
          <button onclick="speakVoice()">Speak</button>
          <button onclick="previewVoice()">Preview</button>
          <button class="danger" onclick="stopVoice()">Stop</button>
        </div>
        <audio id="ttsPreview" controls hidden></audio>
        <div class="card">
          <h2>Voice controls</h2>
          <label for="ttsVoice">Voice style</label>
          <select id="ttsVoice">
            <option value="female">Female — Aria</option><option value="male">Male — Guy</option>
            <option value="deep">Deep — Christopher</option><option value="robotic">Robotic — Andrew</option>
            <option value="funny">Funny — Ana</option>
          </select>
          <div class="slider-line"><label for="ttsVolume">Volume</label><input id="ttsVolume" type="range" min="0" max="200" value="100"><output id="ttsVolumeOut">100%</output></div>
          <div class="slider-line"><label for="ttsSpeed">Speed</label><input id="ttsSpeed" type="range" min="50" max="200" value="100"><output id="ttsSpeedOut">1.00×</output></div>
          <div class="slider-line"><label for="ttsPitch">Pitch</label><input id="ttsPitch" type="range" min="-50" max="50" value="0"><output id="ttsPitchOut">0 Hz</output></div>
        </div>
      </div>
      <aside class="panel">
        <h2>Discord connection</h2>
        <p id="voiceStatus" class="connection">Disconnected</p>
        <label for="ttsActorId">Your Discord user ID</label>
        <input id="ttsActorId" inputmode="numeric" placeholder="Required for owner/role check">
        <label for="ttsVoiceChannels">Voice channel</label>
        <select id="ttsVoiceChannels"></select>
        <div class="row"><button onclick="joinVoice()">Join VC</button><button onclick="leaveVoice()">Leave VC</button></div>
        <p class="status" id="ttsStatus"></p>
        <p>Access is limited to the server owner or users/roles configured by the bot owner.</p>
      </aside>
    </section>
  </div>
<script>
const $ = id => document.getElementById(id);
$('token').value = localStorage.ainToken || '';
$('ttsActorId').value = localStorage.ainTtsActor || '';
function token(){ localStorage.ainToken = $('token').value; return encodeURIComponent($('token').value); }
function guild(){ return $('guilds').value; }
function setStatus(t){ $('status').textContent = t; }
function setTtsStatus(t){ $('ttsStatus').textContent = t; }
function showTab(id, button){ document.querySelectorAll('.tabpage').forEach(x=>x.classList.remove('active')); document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active')); $(id).classList.add('active'); button.classList.add('active'); if(id==='ttsTab') refreshVoiceStatus(); if(id==='panelTab') renderPanelPreview(); }
function showDashboardView(section,button){
  showTab('dashboardTab',button);
  document.querySelectorAll('.dashboard-card').forEach(card=>card.classList.toggle('filtered-out',section!=='overview'&&card.dataset.section!==section));
  if(section==='commands'&&guild()) loadCommands();
}
function ttsPayload(){ localStorage.ainTtsActor=$('ttsActorId').value; return {actor_id:$('ttsActorId').value, channel_id:$('ttsVoiceChannels').value, text:$('ttsText').value, voice:$('ttsVoice').value, volume:Number($('ttsVolume').value), speed:Number($('ttsSpeed').value), pitch:Number($('ttsPitch').value)}; }
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
  $('ttsVoiceChannels').innerHTML = data.voice_channels.map(v=>`<option value="${v.id}">${v.name}</option>`).join('');
  $('textChannels').innerHTML = data.text_channels.map(c=>`<option value="${c.id}">#${c.name}</option>`).join('');
  $('panelChannel').innerHTML = data.text_channels.map(c=>`<option value="${c.id}">#${c.name}</option>`).join('');
  $('members').innerHTML = data.members_list.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
  $('roles').innerHTML = data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
  $('shopRole').innerHTML = `<option value="0">No role reward</option>` + data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
  $('ttsText').maxLength = data.tts_max_length;
  $('ttsCount').parentElement.lastChild.textContent = '/' + data.tts_max_length;
  if(!data.tts_available) setTtsStatus('TTS package missing on the host. Reinstall requirements.txt and redeploy.');
  await loadPanelProfiles();
  refreshVoiceStatus();
}
function panelPayload(){
  localStorage.ainPanelActor=$('panelActorId').value;
  return {actor_id:$('panelActorId').value,name:$('panelName').value,channel_id:$('panelChannel').value,layout:$('panelLayout').value,color:$('panelColor').value,title:$('panelTitle').value,description:$('panelDescription').value,fields:$('panelFields').value,footer:$('panelFooter').value,thumbnail_url:$('panelThumbnail').value};
}
function escPanel(value){return String(value||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function renderPanelPreview(){
  const d=panelPayload(), rows=d.fields.split(/\\r?\\n/).map(v=>v.split('|').map(x=>x.trim())).filter(v=>v[0]).slice(0,25);
  const fields=rows.map(v=>`<div class="preview-field"><b>${escPanel(v[0])}</b><span>${escPanel(v[1]||'')}</span></div>`).join('');
  $('panelPreview').style.borderColor=d.color;
  $('panelPreview').innerHTML=`<h3>${escPanel(d.title||'Command Panel')}</h3><p>${escPanel(d.description)}</p><div class="${d.layout==='cards'?'preview-cards':''}">${fields}</div>${d.layout==='minimal'?'':'<div class="preview-footer">'+escPanel(d.footer)+'</div>'}`;
}
async function loadPanelProfiles(){if(!guild())return;try{const d=await api('/api/guild/'+guild()+'/panel/profiles');const selected=$('panelProfiles').value;$('panelProfiles').innerHTML='<option value="">New interface</option>'+d.names.map(n=>`<option value="${escPanel(n)}">${escPanel(n)}</option>`).join('');if(d.names.includes(selected))$('panelProfiles').value=selected}catch(e){$('panelStatus').textContent=e.message}}
function selectPanelProfile(){if($('panelProfiles').value)loadPanelDesign()}
function newPanelDesign(){$('panelProfiles').value='';$('panelName').value='';$('panelStatus').textContent='New blank name ready. Edit the interface, give it a name, then save.';renderPanelPreview()}
async function loadPanelDesign(){try{const name=$('panelProfiles').value;const d=await api('/api/guild/'+guild()+'/panel'+(name?'?name='+encodeURIComponent(name):''));$('panelName').value=d.name||name||'';Object.entries({panelLayout:d.layout,panelColor:d.color,panelTitle:d.title,panelDescription:d.description,panelFields:d.fields,panelFooter:d.footer,panelThumbnail:d.thumbnail_url}).forEach(([id,v])=>{if(v!==undefined&&v!==null)$(id).value=v});renderPanelPreview();$('panelStatus').textContent=name?'Interface “'+name+'” loaded.':'Default design loaded.'}catch(e){$('panelStatus').textContent=e.message}}
async function savePanelDesign(){try{const name=$('panelName').value.trim();if(!name)throw new Error('Give this interface a name first.');await api('/api/guild/'+guild()+'/panel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(panelPayload())});await loadPanelProfiles();$('panelProfiles').value=name;$('panelStatus').textContent='Interface “'+name+'” saved for this server.';renderPanelPreview()}catch(e){$('panelStatus').textContent=e.message}}
async function deletePanelDesign(){try{const name=$('panelProfiles').value;if(!name)throw new Error('Select a saved interface first.');if(!confirm('Delete “'+name+'”?'))return;await api('/api/guild/'+guild()+'/panel/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({actor_id:$('panelActorId').value,name})});newPanelDesign();await loadPanelProfiles();$('panelStatus').textContent='Interface deleted.'}catch(e){$('panelStatus').textContent=e.message}}
async function sendPanelDesign(){try{await api('/api/guild/'+guild()+'/panel/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(panelPayload())});$('panelStatus').textContent='Panel sent to Discord.'}catch(e){$('panelStatus').textContent=e.message}}
$('panelActorId').value=localStorage.ainPanelActor||'';['panelLayout','panelColor','panelTitle','panelDescription','panelFields','panelFooter','panelThumbnail'].forEach(id=>$(id).addEventListener('input',renderPanelPreview));renderPanelPreview();
function renderCommands(commands){
  $('results').innerHTML = commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join('') || '<p>No commands found.</p>';
}
async function loadCommands(){ const data = await api('/api/guild/' + guild() + '/commands'); renderCommands(data.commands); }
async function search(){ const data = await api('/api/guild/' + guild() + '/search?q=' + encodeURIComponent($('query').value)); renderCommands(data.commands); }
async function askAssistant(){ const data = await api('/api/guild/' + guild() + '/assistant', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({question:$('assistantQuestion').value})}); $('assistantBox').innerHTML = `<p>${data.answer.replaceAll('\\n','<br>')}</p>` + data.commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join(''); setStatus('Assistant answered.'); }
async function savePrefix(){ await api('/api/guild/' + guild() + '/prefix', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({prefix:$('prefix').value})}); setStatus('Prefix saved.'); loadSummary(); }
async function saveTheme(){ await api('/api/guild/' + guild() + '/theme', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({color:$('color').value})}); setStatus('Theme saved.'); }
async function feature(enabled){ await api('/api/guild/' + guild() + '/feature', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({feature:$('feature').value, enabled})}); setStatus('Feature updated.'); }
async function joinVoice(){ try { const data=await api('/api/guild/' + guild() + '/voice/join', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(ttsPayload())}); setTtsStatus('Connected to ' + data.channel + '.'); await refreshVoiceStatus(); } catch(e){ setTtsStatus(e.message); } }
async function leaveVoice(){ try { await api('/api/guild/' + guild() + '/voice/leave', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(ttsPayload())}); setTtsStatus('Bot left the voice channel.'); await refreshVoiceStatus(); } catch(e){ setTtsStatus(e.message); } }
async function speakVoice(){ try { const data=await api('/api/guild/' + guild() + '/voice/speak', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(ttsPayload())}); setTtsStatus(`Added to queue (${data.queued}).`); $('ttsText').value=''; $('ttsCount').textContent='0'; await refreshVoiceStatus(); } catch(e){ setTtsStatus(e.message); } }
async function stopVoice(){ try { await api('/api/guild/' + guild() + '/voice/stop', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(ttsPayload())}); setTtsStatus('Playback stopped and queue cleared.'); await refreshVoiceStatus(); } catch(e){ setTtsStatus(e.message); } }
async function refreshVoiceStatus(){ if(!guild()) return; try { const data=await api('/api/guild/' + guild() + '/voice/status'); const el=$('voiceStatus'); el.classList.toggle('online',data.connected); el.textContent=data.connected ? `${data.channel} · ${data.playing?'Speaking':'Ready'} · ${data.queued} queued` : 'Disconnected'; } catch(e){ $('voiceStatus').textContent=e.message; } }
async function previewVoice(){ try { setTtsStatus('Generating preview…'); const res=await fetch('/api/guild/'+guild()+'/voice/preview?token='+token(), {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(ttsPayload())}); const error=await res.clone().json().catch(()=>null); if(!res.ok) throw new Error(error?.error||'Preview failed'); const player=$('ttsPreview'); if(player.src) URL.revokeObjectURL(player.src); player.src=URL.createObjectURL(await res.blob()); player.hidden=false; await player.play(); setTtsStatus('Preview playing in this browser only.'); } catch(e){ setTtsStatus(e.message); } }
async function sendBotMessage(){ await api('/api/guild/' + guild() + '/message', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({channel_id:$('textChannels').value, message:$('botMessage').value})}); setStatus('Message sent as bot.'); $('botMessage').value=''; }
async function sendEmbed(){ await api('/api/guild/' + guild() + '/embed', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({channel_id:$('textChannels').value, title:$('embedTitle').value, message:$('embedText').value})}); setStatus('Embed sent.'); }
async function roleAction(action){ await api('/api/guild/' + guild() + '/member/role', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, role_id:$('roles').value, action})}); setStatus('Role updated.'); }
async function timeoutMember(){ await api('/api/guild/' + guild() + '/member/timeout', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, minutes:10})}); setStatus('Member timed out for 10 minutes.'); }
async function untimeoutMember(){ await api('/api/guild/' + guild() + '/member/untimeout', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Timeout removed.'); }
async function moveMember(){ await api('/api/guild/' + guild() + '/member/move', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, channel_id:$('voiceChannels').value})}); setStatus('Member moved.'); }
async function disconnectMember(){ await api('/api/guild/' + guild() + '/member/disconnect', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member disconnected.'); }
async function kickMember(){ if(confirm('Kick this member?')){ await api('/api/guild/' + guild() + '/member/kick', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member kicked.'); } }
async function banMember(){ if(confirm('Ban this member?')){ await api('/api/guild/' + guild() + '/member/ban', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value})}); setStatus('Member banned.'); } }
async function music(action){ const data = await api('/api/guild/' + guild() + '/music/' + action, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({query:$('musicQuery').value, channel_id:$('voiceChannels').value, text_channel_id:$('textChannels').value, volume:$('musicVolume').value})}); setStatus(data.message || 'Music updated.'); if(data.status){ $('musicBox').innerHTML = `<p>${data.status}</p>`; } }
async function backup(){ const data = await api('/api/guild/' + guild() + '/backup/create', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({})}); $('backupBox').innerHTML = `Backup code: <b>${data.code}</b>`; setStatus('Backup code created.'); }
async function antinuke(enabled){ await api('/api/guild/' + guild() + '/antinuke/set', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({enabled})}); setStatus('Anti-nuke updated.'); }
async function antiWhitelist(type){ await api('/api/guild/' + guild() + '/antinuke/whitelist', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({target_id:type === 'role' ? $('roles').value : $('members').value})}); setStatus('Anti-nuke whitelist updated.'); }
async function coins(action){ await api('/api/guild/' + guild() + '/economy/' + action, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({member_id:$('members').value, amount:$('coins').value})}); setStatus('Economy updated.'); }
async function shopLoad(){ const data = await api('/api/guild/' + guild() + '/shop'); $('shopBox').innerHTML = data.items.map(i=>`<div class="cmd"><b>${i.name} - ${i.price}</b><span>${i.description}${i.role_id ? ' | role ' + i.role_id : ''}</span></div>`).join('') || '<p>No custom shop items.</p>'; setStatus('Shop loaded.'); }
async function shopSave(){ await api('/api/guild/' + guild() + '/shop/item', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({name:$('shopKey').value, price:$('shopPrice').value, description:$('shopDescription').value, role_id:$('shopRole').value})}); setStatus('Shop item saved.'); await shopLoad(); }
async function shopDelete(){ await api('/api/guild/' + guild() + '/shop/delete', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({name:$('shopKey').value})}); setStatus('Shop item deleted.'); await shopLoad(); }
async function createRole(){ await api('/api/guild/' + guild() + '/role/create', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({name:$('roleName').value, color:$('roleColor').value})}); setStatus('Role created.'); await loadSummary(); }
async function renameRole(){ await api('/api/guild/' + guild() + '/role/rename', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({role_id:$('roles').value, name:$('roleName').value})}); setStatus('Role renamed.'); await loadSummary(); }
async function moveRoleTop(){ await api('/api/guild/' + guild() + '/role/move_top', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({role_id:$('roles').value})}); setStatus('Role moved.'); await loadSummary(); }
async function loadLogs(){ const data = await api('/api/guild/' + guild() + '/logs'); $('logsBox').innerHTML = data.logs.map(l=>`<div class="cmd"><b>${l.event}</b><span>${l.text}</span></div>`).join('') || '<p>No logs yet.</p>'; setStatus('Logs loaded.'); }
$('ttsText').addEventListener('input',()=>{$('ttsCount').textContent=$('ttsText').value.length});
$('ttsVolume').addEventListener('input',()=>{$('ttsVolumeOut').textContent=$('ttsVolume').value+'%'});
$('ttsSpeed').addEventListener('input',()=>{$('ttsSpeedOut').textContent=(Number($('ttsSpeed').value)/100).toFixed(2)+'×'});
$('ttsPitch').addEventListener('input',()=>{$('ttsPitchOut').textContent=$('ttsPitch').value+' Hz'});
setInterval(()=>{ if($('ttsTab').classList.contains('active')) refreshVoiceStatus(); },5000);
</script>
</body>
</html>"""


class Dashboard:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.tts_queues: dict[int, asyncio.Queue[dict[str, Any]]] = {}
        self.tts_workers: dict[int, asyncio.Task[None]] = {}
        self.tts_cooldowns: dict[tuple[int, int], float] = {}
        self.tts_generation_lock = asyncio.Semaphore(2)

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

    @staticmethod
    def _env_ids(name: str) -> set[int]:
        return {int(value.strip()) for value in os.getenv(name, "").split(",") if value.strip().isdigit()}

    def require_tts_controller(self, guild: discord.Guild, body: dict[str, Any]) -> discord.Member:
        actor_id = int(body.get("actor_id", 0) or 0)
        member = guild.get_member(actor_id)
        if member is None:
            raise web.HTTPForbidden(text=json.dumps({"error": "Enter your Discord user ID to use Text to Speech."}), content_type="application/json")
        allowed_users = self._env_ids("TTS_ALLOWED_USER_IDS") | set(getattr(self.bot.settings, "owner_ids", set()))
        allowed_roles = self._env_ids("TTS_ALLOWED_ROLE_IDS")
        allowed = member.id == guild.owner_id or member.id in allowed_users or any(role.id in allowed_roles for role in member.roles)
        if not allowed:
            raise web.HTTPForbidden(text=json.dumps({"error": "Only the server owner or an approved TTS user/role can use this control."}), content_type="application/json")
        return member

    @staticmethod
    def require_tts_backend() -> None:
        if edge_tts is None:
            raise web.HTTPServiceUnavailable(
                text=json.dumps({"error": "Text to Speech is unavailable because edge-tts is not installed. Redeploy after installing requirements.txt."}),
                content_type="application/json",
            )

    def require_panel_controller(self, guild: discord.Guild, body: dict[str, Any]) -> discord.Member:
        actor_id = int(body.get("actor_id", 0) or 0)
        member = guild.get_member(actor_id)
        if member is None:
            raise web.HTTPForbidden(text=json.dumps({"error": "Enter your Discord user ID to edit server panels."}), content_type="application/json")
        allowed_users = self._env_ids("PANEL_ALLOWED_USER_IDS") | set(getattr(self.bot.settings, "owner_ids", set()))
        allowed_roles = self._env_ids("PANEL_ALLOWED_ROLE_IDS")
        allowed = member.id == guild.owner_id or member.id in allowed_users or any(role.id in allowed_roles for role in member.roles)
        if not allowed:
            raise web.HTTPForbidden(text=json.dumps({"error": "Only the server owner or an approved panel user/role can edit panels."}), content_type="application/json")
        return member

    @staticmethod
    def panel_defaults() -> dict[str, Any]:
        return {
            "layout": "compact",
            "color": "#5865f2",
            "title": "Voice Channel Controls",
            "description": "Manage your temporary voice channels with the commands below.",
            "fields": "/vc count | View active users\n/vc rename <name> | Rename your room\n/vc lock | Lock room\n/vc unlock | Unlock room\n/vc permit <user> | Permit user\n/vc reject <user> | Reject user\n/vc limit <1-100> | Set room limit\n/vc transfer <user> | Transfer ownership",
            "footer": "AIN Bot • Server controls",
            "thumbnail_url": "",
        }

    def normalize_panel(self, body: dict[str, Any]) -> dict[str, Any]:
        defaults = self.panel_defaults()
        layout = str(body.get("layout", defaults["layout"]))
        if layout not in {"compact", "cards", "minimal"}:
            layout = "compact"
        color = str(body.get("color", defaults["color"])).strip()
        if len(color) != 7 or not color.startswith("#"):
            color = defaults["color"]
        try:
            int(color[1:], 16)
        except ValueError:
            color = defaults["color"]
        thumbnail = str(body.get("thumbnail_url", "")).strip()[:500]
        if thumbnail and not thumbnail.startswith(("https://", "http://")):
            thumbnail = ""
        return {
            "layout": layout,
            "color": color,
            "title": str(body.get("title", defaults["title"])).strip()[:120] or defaults["title"],
            "description": str(body.get("description", defaults["description"])).strip()[:1000],
            "fields": str(body.get("fields", defaults["fields"])).strip()[:3500],
            "footer": str(body.get("footer", defaults["footer"])).strip()[:200],
            "thumbnail_url": thumbnail,
        }

    @staticmethod
    def normalize_panel_name(value: Any) -> str:
        name = " ".join(str(value or "").strip().split())[:40]
        if any(character in name for character in "<>\\/\x00"):
            return ""
        return name

    def make_panel_embed(self, design: dict[str, Any]) -> discord.Embed:
        rows: list[tuple[str, str]] = []
        for line in design["fields"].splitlines():
            if not line.strip():
                continue
            command, _, explanation = line.partition("|")
            rows.append((command.strip()[:256], explanation.strip()[:1024]))
            if len(rows) >= 25:
                break
        color = discord.Color(int(design["color"][1:], 16))
        embed_out = discord.Embed(title=design["title"], description=design["description"] or None, color=color)
        if design["layout"] == "compact":
            lines = ["**Commands**                         **Usage**"]
            lines.extend(f"`{command}`\n{explanation}" for command, explanation in rows)
            embed_out.description = (((design["description"] + "\n\n") if design["description"] else "") + "\n".join(lines))[:4096]
        elif design["layout"] == "cards":
            for command, explanation in rows:
                embed_out.add_field(name=command, value=explanation or "—", inline=True)
        else:
            lines = [f"**{command}** — {explanation}" if explanation else f"**{command}**" for command, explanation in rows]
            embed_out.description = (((design["description"] + "\n\n") if design["description"] else "") + "\n".join(lines))[:4096]
        if design["footer"]:
            embed_out.set_footer(text=design["footer"])
        if design["thumbnail_url"]:
            embed_out.set_thumbnail(url=design["thumbnail_url"])
        return embed_out

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
            "tts_max_length": max(50, min(int(os.getenv("TTS_MAX_LENGTH", "500")), 900)),
            "tts_available": edge_tts is not None,
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

    def command_matches(self, question: str, limit: int = 8) -> list[dict[str, str]]:
        words = [word for word in question.lower().replace("/", " ").replace(",", " ").split() if len(word) > 1]
        synonyms = {
            "raid": ["antinuke", "security", "lockdown"],
            "nuke": ["antinuke", "whitelist", "security"],
            "voice": ["vc", "jtc", "music"],
            "call": ["vc", "jtc", "voice"],
            "song": ["music", "play", "queue"],
            "coins": ["economy", "wallet", "shop"],
            "money": ["economy", "wallet", "shop"],
            "backup": ["backup", "restore"],
            "role": ["role", "ownerrole", "autorole"],
            "ticket": ["ticket"],
            "welcome": ["welcome"],
            "logs": ["logs", "usagelogs"],
        }
        expanded = set(words)
        for word in list(words):
            expanded.update(synonyms.get(word, []))
        scored = []
        for item in self.command_list():
            haystack = f"{item['name']} {item['description']}".lower()
            score = sum(2 if word in item["name"].lower() else 1 for word in expanded if word in haystack)
            if score:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
        return [item for _, item in scored[:limit]]

    async def assistant(self, request: web.Request) -> web.Response:
        self.require_token(request)
        self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        question = str(body.get("question", "")).strip()[:900]
        if not question:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Ask a question first."}), content_type="application/json")
        matches = self.command_matches(question)
        fallback = "Here are the commands I would try first:\n" + "\n".join(f"- {item['name']}: {item['description']}" for item in matches[:5])
        fallback += "\n\nTip: run the command in Discord, or use the matching dashboard panel if it exists."
        api_key = getattr(self.bot.settings, "openai_api_key", None)
        if not api_key:
            return web.json_response({"answer": fallback, "commands": matches})
        prompt = (
            "You are a Discord bot command helper. Answer briefly and only suggest commands from this list.\n"
            f"Question: {question}\n"
            "Commands:\n"
            + "\n".join(f"{item['name']} - {item['description']}" for item in matches[:12])
        )
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": os.getenv("OPENAI_DASHBOARD_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 350,
        }
        try:
            async with ClientSession() as session:
                async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as response:
                    if response.status >= 400:
                        return web.json_response({"answer": fallback, "commands": matches})
                    data = await response.json()
                    answer = data["choices"][0]["message"]["content"]
                    return web.json_response({"answer": answer[:1800], "commands": matches})
        except Exception:
            return web.json_response({"answer": fallback, "commands": matches})

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
        raw_value = str(body.get("color", "#b2182c")).strip()
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        theme = settings.get("theme", {})
        if is_multicolor_theme(raw_value):
            theme["mode"] = "fade"
            theme["fade_speed"] = 10
            await self.bot.db.set_settings_value(guild.id, "theme", theme, self.bot.settings.default_prefix)
            theme_options = getattr(self.bot, "theme_options", {})
            theme_options[guild.id] = theme
            setattr(self.bot, "theme_options", theme_options)
            return web.json_response({"ok": True, "mode": "fade"})
        raw = raw_value.lstrip("#")
        color = int(raw, 16) if len(raw) == 6 else 0xB2182C
        theme["color"] = color
        theme["mode"] = "solid"
        await self.bot.db.set_settings_value(guild.id, "theme", theme, self.bot.settings.default_prefix)
        theme_options = getattr(self.bot, "theme_options", {})
        theme_options[guild.id] = theme
        setattr(self.bot, "theme_options", theme_options)
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
        self.require_tts_controller(guild, body)
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
        body = await request.json()
        self.require_tts_controller(guild, body)
        await self._stop_tts(guild)
        current = guild.voice_client
        if current and current.is_connected():
            await current.disconnect(force=True)
        return web.json_response({"ok": True})

    TTS_VOICES = {
        "female": ("en-US-AriaNeural", 0),
        "male": ("en-US-GuyNeural", 0),
        "deep": ("en-US-ChristopherNeural", -12),
        "robotic": ("en-US-AndrewMultilingualNeural", -4),
        "funny": ("en-US-AnaNeural", 16),
    }

    async def make_tts_file(self, text: str, voice: str, volume: int, speed: int, pitch: int) -> Path:
        self.require_tts_backend()
        voice_name, style_pitch = self.TTS_VOICES.get(voice, self.TTS_VOICES["female"])
        path = Path(tempfile.gettempdir()) / f"ainbot-tts-{os.getpid()}-{time.time_ns()}.mp3"
        communicate = edge_tts.Communicate(
            text,
            voice_name,
            rate=f"{speed - 100:+d}%",
            volume=f"{volume - 100:+d}%",
            pitch=f"{pitch + style_pitch:+d}Hz",
        )
        try:
            async with self.tts_generation_lock:
                await asyncio.wait_for(communicate.save(str(path)), timeout=30)
        except Exception as exc:
            path.unlink(missing_ok=True)
            self.bot.log.warning("TTS generation failed: %s", exc)
            raise RuntimeError("The free TTS service could not create audio. Check internet access and try again.") from exc
        return path

    async def _stop_tts(self, guild: discord.Guild) -> None:
        worker = self.tts_workers.pop(guild.id, None)
        if worker and worker is not asyncio.current_task() and not worker.done():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        queue = self.tts_queues.get(guild.id)
        if queue:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break
        current = guild.voice_client
        if current and (current.is_playing() or current.is_paused()):
            current.stop()

    async def _tts_worker(self, guild: discord.Guild) -> None:
        queue = self.tts_queues[guild.id]
        try:
            while True:
                job = await queue.get()
                audio_path: Path | None = None
                try:
                    current = guild.voice_client
                    channel = guild.get_channel(job["channel_id"])
                    if not isinstance(channel, discord.VoiceChannel):
                        continue
                    if current is None or not current.is_connected():
                        current = await channel.connect(self_deaf=True)
                    elif current.channel != channel:
                        await current.move_to(channel)
                    audio_path = await self.make_tts_file(job["text"], job["voice"], job["volume"], job["speed"], job["pitch"])
                    finished = asyncio.Event()
                    loop = asyncio.get_running_loop()
                    source = discord.FFmpegPCMAudio(str(audio_path), executable=ffmpeg_executable())
                    current.play(source, after=lambda error: loop.call_soon_threadsafe(finished.set))
                    await asyncio.wait_for(finished.wait(), timeout=180)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.bot.log.exception("Queued dashboard TTS failed in guild %s", guild.id)
                finally:
                    if audio_path:
                        audio_path.unlink(missing_ok=True)
                    queue.task_done()
        except asyncio.CancelledError:
            current = guild.voice_client
            if current and (current.is_playing() or current.is_paused()):
                current.stop()

    async def speak_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        self.require_tts_backend()
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        actor = self.require_tts_controller(guild, body)
        text = str(body.get("text", "")).strip()
        if not text:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Type something for the bot to say."}), content_type="application/json")
        max_length = max(50, min(int(os.getenv("TTS_MAX_LENGTH", "500")), 900))
        if len(text) > max_length:
            raise web.HTTPBadRequest(text=json.dumps({"error": f"Text is limited to {max_length} characters."}), content_type="application/json")
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        if not isinstance(channel, discord.VoiceChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid voice channel."}), content_type="application/json")
        cooldown = max(1, int(os.getenv("TTS_COOLDOWN_SECONDS", "5")))
        key = (guild.id, actor.id)
        remaining = self.tts_cooldowns.get(key, 0) - time.monotonic()
        if remaining > 0:
            raise web.HTTPTooManyRequests(text=json.dumps({"error": f"Please wait {remaining:.1f} seconds before speaking again."}), content_type="application/json")
        queue = self.tts_queues.setdefault(guild.id, asyncio.Queue(maxsize=max(1, int(os.getenv("TTS_QUEUE_LIMIT", "3")))))
        if queue.full():
            raise web.HTTPTooManyRequests(text=json.dumps({"error": "The TTS queue is full. Wait or press Stop."}), content_type="application/json")
        job = {
            "text": text,
            "voice": str(body.get("voice", "female")),
            "channel_id": channel.id,
            "volume": max(0, min(int(body.get("volume", 100)), 200)),
            "speed": max(50, min(int(body.get("speed", 100)), 200)),
            "pitch": max(-50, min(int(body.get("pitch", 0)), 50)),
        }
        await queue.put(job)
        self.tts_cooldowns[key] = time.monotonic() + cooldown
        worker = self.tts_workers.get(guild.id)
        if worker is None or worker.done():
            self.tts_workers[guild.id] = asyncio.create_task(self._tts_worker(guild))
        return web.json_response({"ok": True, "queued": queue.qsize()})

    async def stop_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        self.require_tts_controller(guild, body)
        await self._stop_tts(guild)
        return web.json_response({"ok": True})

    async def voice_status(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        current = guild.voice_client
        connected = bool(current and current.is_connected())
        return web.json_response({
            "connected": connected,
            "channel": current.channel.name if connected and current.channel else None,
            "playing": bool(current and current.is_playing()),
            "queued": self.tts_queues.get(guild.id).qsize() if guild.id in self.tts_queues else 0,
        })

    async def preview_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        self.require_tts_backend()
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        self.require_tts_controller(guild, body)
        text = str(body.get("text") or "Hello! This is your selected AIN Bot voice.").strip()[:160]
        path = await self.make_tts_file(
            text, str(body.get("voice", "female")),
            max(0, min(int(body.get("volume", 100)), 200)),
            max(50, min(int(body.get("speed", 100)), 200)),
            max(-50, min(int(body.get("pitch", 0)), 50)),
        )
        try:
            return web.Response(body=path.read_bytes(), content_type="audio/mpeg")
        finally:
            path.unlink(missing_ok=True)

    async def panel_get(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        design = self.panel_defaults()
        name = self.normalize_panel_name(request.query.get("name"))
        saved = settings.get("panel_designs", {})
        design.update(saved.get(name, {}) if name else settings.get("panel_design", {}))
        payload = self.normalize_panel(design)
        payload["name"] = name
        return web.json_response(payload)

    async def panel_profiles(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        names = sorted((name for name in settings.get("panel_designs", {}) if self.normalize_panel_name(name)), key=str.lower)
        return web.json_response({"names": names[:20]})

    async def panel_save(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        actor = self.require_panel_controller(guild, body)
        name = self.normalize_panel_name(body.get("name"))
        if not name:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Give this interface a valid name first."}), content_type="application/json")
        design = self.normalize_panel(body)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        designs = settings.get("panel_designs", {})
        if name not in designs and len(designs) >= 20:
            raise web.HTTPBadRequest(text=json.dumps({"error": "This server can save up to 20 interfaces. Delete one before adding another."}), content_type="application/json")
        designs[name] = design
        await self.bot.db.set_settings_value(guild.id, "panel_designs", designs, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "panel_design", design, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "name": name, "saved_by": str(actor.id), "design": design})

    async def panel_delete(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        actor = self.require_panel_controller(guild, body)
        name = self.normalize_panel_name(body.get("name"))
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        designs = settings.get("panel_designs", {})
        if name not in designs:
            raise web.HTTPNotFound(text=json.dumps({"error": "That saved interface was not found."}), content_type="application/json")
        designs.pop(name, None)
        await self.bot.db.set_settings_value(guild.id, "panel_designs", designs, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "deleted": name, "deleted_by": str(actor.id)})

    async def panel_send(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        actor = self.require_panel_controller(guild, body)
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid text channel."}), content_type="application/json")
        permissions = channel.permissions_for(guild.me)
        if not permissions.send_messages or not permissions.embed_links:
            raise web.HTTPForbidden(text=json.dumps({"error": "AIN needs Send Messages and Embed Links in that channel."}), content_type="application/json")
        design = self.normalize_panel(body)
        await self.bot.db.set_settings_value(guild.id, "panel_design", design, self.bot.settings.default_prefix)
        message = await channel.send(embed=self.make_panel_embed(design))
        return web.json_response({"ok": True, "message_id": str(message.id), "sent_by": str(actor.id)})

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

    async def send_embed(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a valid text channel."}), content_type="application/json")
        title = str(body.get("title", "Announcement")).strip()[:120] or "Announcement"
        message = str(body.get("message", "")).strip()[:3500]
        if not message:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Embed message cannot be empty."}), content_type="application/json")
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        color = theme_color_from_data(settings.get("theme", {}), discord.Color(0xB2182C))
        await channel.send(embed=discord.Embed(title=title, description=message, color=color))
        return web.json_response({"ok": True})

    async def music_status(self, guild: discord.Guild) -> dict[str, str]:
        cog = self.bot.get_cog("Music")
        if cog is None:
            return {"status": "Music cog is not loaded."}
        player = cog.manager.get(guild)
        vc = guild.voice_client
        state = "disconnected"
        if vc and vc.is_playing():
            state = "playing"
        elif vc and vc.is_paused():
            state = "paused"
        elif vc:
            state = "connected"
        current = player.current.title if player.current else "Nothing"
        return {"status": f"{state} | now: {current} | queue: {player.queue.qsize()} | volume: {int(player.volume * 100)}%"}

    async def music_action(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        action = request.match_info["action"]
        body = await request.json()
        cog = self.bot.get_cog("Music")
        if cog is None:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Music cog is not loaded."}), content_type="application/json")
        player = cog.manager.get(guild)
        vc = guild.voice_client
        if action == "add":
            query = str(body.get("query", "")).strip()
            if not query:
                raise web.HTTPBadRequest(text=json.dumps({"error": "Type a song or URL."}), content_type="application/json")
            channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
            if vc is None or not vc.is_connected():
                if not isinstance(channel, discord.VoiceChannel):
                    raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a voice channel first."}), content_type="application/json")
                vc = await channel.connect(self_deaf=True)
            tracks = await player.resolve(query, self.bot.user.id if self.bot.user else 0)
            for track in tracks[:50]:
                await player.queue.put(track)
            return web.json_response({"ok": True, "message": f"Added {len(tracks[:50])} track(s).", **await self.music_status(guild)})
        if action == "play":
            text_channel = guild.get_channel(int(body.get("text_channel_id", 0) or 0))
            if vc is None or not vc.is_connected():
                channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
                if not isinstance(channel, discord.VoiceChannel):
                    raise web.HTTPBadRequest(text=json.dumps({"error": "Pick a voice channel first."}), content_type="application/json")
                vc = await channel.connect(self_deaf=True)
            if not vc.is_playing() and not player.queue.empty():
                await cog.play_next(guild, text_channel if isinstance(text_channel, discord.TextChannel) else guild.system_channel)
            return web.json_response({"ok": True, "message": "Playback started.", **await self.music_status(guild)})
        if action == "pause" and vc:
            vc.pause()
        elif action == "resume" and vc:
            vc.resume()
        elif action == "skip" and vc:
            vc.stop()
        elif action == "stop":
            while not player.queue.empty():
                player.queue.get_nowait()
            player.current = None
            if vc:
                vc.stop()
        elif action == "loop":
            player.loop_one = not player.loop_one
        elif action == "shuffle":
            import random
            items = list(player.queue._queue)
            random.shuffle(items)
            player.queue._queue.clear()
            for item in items:
                player.queue._queue.append(item)
        elif action == "volume":
            player.volume = max(0.01, min(int(body.get("volume", 70) or 70), 200)) / 100
            if vc and vc.source and hasattr(vc.source, "volume"):
                vc.source.volume = player.volume
        return web.json_response({"ok": True, "message": f"Music {action} done.", **await self.music_status(guild)})

    async def create_backup(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        cog = self.bot.get_cog("ServerBackup")
        if cog is None:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Backup cog is not loaded."}), content_type="application/json")
        code = make_code()
        snapshot = await cog.snapshot(guild)
        await self.bot.db.execute(
            "INSERT INTO backup_codes(code,guild_id,creator_id,snapshot) VALUES(?,?,?,?)",
            code,
            guild.id,
            self.bot.user.id if self.bot.user else 0,
            json.dumps(snapshot),
        )
        return web.json_response({"ok": True, "code": code})

    async def antinuke_set(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        await self.bot.db.set_settings_value(guild.id, "antinuke_enabled", bool(body.get("enabled", True)), self.bot.settings.default_prefix)
        return web.json_response({"ok": True})

    async def antinuke_whitelist(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        target_id = int(body.get("target_id", 0) or 0)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        whitelist = settings.get("antinuke_whitelist", [])
        if target_id and target_id not in whitelist:
            whitelist.append(target_id)
        await self.bot.db.set_settings_value(guild.id, "antinuke_whitelist", whitelist, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "count": len(whitelist)})

    async def economy_action(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        action = request.match_info["action"]
        body = await request.json()
        member = self.get_member_or_404(guild, body.get("member_id"))
        amount = max(0, min(int(body.get("amount", 0) or 0), 100_000_000))
        await self.bot.db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)", guild.id, member.id)
        if action == "take":
            await self.bot.db.execute("UPDATE economy SET wallet=max(wallet-?,0) WHERE guild_id=? AND user_id=?", amount, guild.id, member.id)
        elif action == "set":
            await self.bot.db.execute("UPDATE economy SET wallet=? WHERE guild_id=? AND user_id=?", amount, guild.id, member.id)
        else:
            await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", amount, guild.id, member.id)
        row = await self.bot.db.fetchrow("SELECT wallet,bank FROM economy WHERE guild_id=? AND user_id=?", guild.id, member.id)
        return web.json_response({"ok": True, "wallet": row["wallet"], "bank": row["bank"]})

    async def shop_list(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        items = []
        for name, data in settings.get("economy_shop", {}).items():
            if isinstance(data, dict):
                items.append({
                    "name": name,
                    "price": int(data.get("price", 0) or 0),
                    "description": str(data.get("description", "")),
                    "role_id": int(data.get("role_id", 0) or 0),
                })
        return web.json_response({"items": sorted(items, key=lambda item: item["name"])})

    async def shop_item_save(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        name = str(body.get("name", "")).strip().lower().replace(" ", "-")[:40]
        if not name:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Item key is required."}), content_type="application/json")
        price = max(0, min(int(body.get("price", 0) or 0), 100_000_000))
        description = str(body.get("description", "Custom shop item."))[:300]
        role_id = int(body.get("role_id", 0) or 0)
        if role_id:
            role = guild.get_role(role_id)
            if role is None:
                raise web.HTTPBadRequest(text=json.dumps({"error": "Reward role does not exist."}), content_type="application/json")
            self.require_manageable_role(guild, role)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        shop = settings.get("economy_shop", {})
        shop[name] = {"price": price, "description": description, "role_id": role_id}
        await self.bot.db.set_settings_value(guild.id, "economy_shop", shop, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "item": name})

    async def shop_item_delete(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        name = str(body.get("name", "")).strip().lower().replace(" ", "-")[:40]
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        shop = settings.get("economy_shop", {})
        shop.pop(name, None)
        await self.bot.db.set_settings_value(guild.id, "economy_shop", shop, self.bot.settings.default_prefix)
        return web.json_response({"ok": True})

    async def create_role(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        name = str(body.get("name", "Dashboard Role")).strip()[:100] or "Dashboard Role"
        raw = str(body.get("color", "#b2182c")).strip().lstrip("#")
        color = int(raw, 16) if len(raw) == 6 else 0xB2182C
        role = await guild.create_role(name=name, color=discord.Color(color), reason="Dashboard role create")
        if guild.me:
            await role.edit(position=max(guild.me.top_role.position - 1, 1), reason="Dashboard role move")
        return web.json_response({"ok": True, "role_id": str(role.id)})

    async def rename_role(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        role = self.get_role_or_404(guild, body.get("role_id"))
        self.require_manageable_role(guild, role)
        name = str(body.get("name", role.name)).strip()[:100] or role.name
        await role.edit(name=name, reason="Dashboard role rename")
        return web.json_response({"ok": True})

    async def move_role_top(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        role = self.get_role_or_404(guild, body.get("role_id"))
        self.require_manageable_role(guild, role)
        await role.edit(position=max(guild.me.top_role.position - 1, 1), reason="Dashboard role move")
        return web.json_response({"ok": True})

    async def logs(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        rows = await self.bot.db.fetchall("SELECT actor_id,target_id,event,data,created_at FROM audit_events WHERE guild_id=? ORDER BY id DESC LIMIT 20", guild.id)
        logs = []
        for row in rows:
            data = json.loads(row["data"] or "{}")
            text = data.get("command") or data.get("status") or json.dumps(data)[:160]
            logs.append({"event": row["event"], "text": f"{row['created_at']} | actor {row['actor_id']} | target {row['target_id']} | {text}"})
        failed = getattr(self.bot, "failed_cogs", {})
        for name, reason in failed.items():
            logs.insert(0, {"event": "failed_cog", "text": f"{name}: {reason}"})
        return web.json_response({"logs": logs[:25]})

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
    @web.middleware
    async def json_errors(request: web.Request, handler: Any) -> web.StreamResponse:
        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text=json.dumps({"error": "One or more values were invalid."}), content_type="application/json")
        except Exception:
            bot.log.exception("Dashboard request failed: %s %s", request.method, request.path)
            raise web.HTTPInternalServerError(text=json.dumps({"error": "The bot could not complete that request. Check the bot logs."}), content_type="application/json")

    dashboard = Dashboard(bot)
    app = web.Application(middlewares=[json_errors])
    app.router.add_get("/", dashboard.index)
    app.router.add_get("/api/guilds", dashboard.guilds)
    app.router.add_get("/api/guild/{guild_id}/summary", dashboard.summary)
    app.router.add_get("/api/guild/{guild_id}/commands", dashboard.commands)
    app.router.add_get("/api/guild/{guild_id}/search", dashboard.search)
    app.router.add_post("/api/guild/{guild_id}/assistant", dashboard.assistant)
    app.router.add_post("/api/guild/{guild_id}/prefix", dashboard.set_prefix)
    app.router.add_post("/api/guild/{guild_id}/theme", dashboard.set_theme)
    app.router.add_post("/api/guild/{guild_id}/feature", dashboard.set_feature)
    app.router.add_post("/api/guild/{guild_id}/voice/join", dashboard.join_voice)
    app.router.add_post("/api/guild/{guild_id}/voice/leave", dashboard.leave_voice)
    app.router.add_post("/api/guild/{guild_id}/voice/speak", dashboard.speak_voice)
    app.router.add_post("/api/guild/{guild_id}/voice/stop", dashboard.stop_voice)
    app.router.add_get("/api/guild/{guild_id}/voice/status", dashboard.voice_status)
    app.router.add_post("/api/guild/{guild_id}/voice/preview", dashboard.preview_voice)
    app.router.add_get("/api/guild/{guild_id}/panel", dashboard.panel_get)
    app.router.add_get("/api/guild/{guild_id}/panel/profiles", dashboard.panel_profiles)
    app.router.add_post("/api/guild/{guild_id}/panel", dashboard.panel_save)
    app.router.add_post("/api/guild/{guild_id}/panel/delete", dashboard.panel_delete)
    app.router.add_post("/api/guild/{guild_id}/panel/send", dashboard.panel_send)
    app.router.add_post("/api/guild/{guild_id}/message", dashboard.send_message)
    app.router.add_post("/api/guild/{guild_id}/embed", dashboard.send_embed)
    app.router.add_post("/api/guild/{guild_id}/music/{action}", dashboard.music_action)
    app.router.add_post("/api/guild/{guild_id}/backup/create", dashboard.create_backup)
    app.router.add_post("/api/guild/{guild_id}/antinuke/set", dashboard.antinuke_set)
    app.router.add_post("/api/guild/{guild_id}/antinuke/whitelist", dashboard.antinuke_whitelist)
    app.router.add_post("/api/guild/{guild_id}/economy/{action}", dashboard.economy_action)
    app.router.add_get("/api/guild/{guild_id}/shop", dashboard.shop_list)
    app.router.add_post("/api/guild/{guild_id}/shop/item", dashboard.shop_item_save)
    app.router.add_post("/api/guild/{guild_id}/shop/delete", dashboard.shop_item_delete)
    app.router.add_post("/api/guild/{guild_id}/role/create", dashboard.create_role)
    app.router.add_post("/api/guild/{guild_id}/role/rename", dashboard.rename_role)
    app.router.add_post("/api/guild/{guild_id}/role/move_top", dashboard.move_role_top)
    app.router.add_get("/api/guild/{guild_id}/logs", dashboard.logs)
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
