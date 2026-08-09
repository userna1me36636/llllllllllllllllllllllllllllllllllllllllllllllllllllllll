from __future__ import annotations

import html
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
import time
import urllib.parse
from typing import Any
import datetime as dt
from pathlib import Path

import discord
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
    .tabs { display:flex; gap:7px; overflow-x:auto; padding:2px 0 12px; margin-bottom:4px; scrollbar-width:thin; }
    .tab-button { white-space:nowrap; background:rgba(255,255,255,.055); color:var(--muted); }
    .tab-button.active { color:#fff; border-color:var(--hot); background:linear-gradient(135deg,rgba(255,56,100,.38),rgba(143,92,255,.28)); }
    .tab-panel { display:none; }
    .tab-panel.active { display:block; }
    .notice { border-left:3px solid var(--c); padding:10px 12px; background:rgba(32,211,255,.08); color:var(--muted); }
    .metric { font-size:34px; font-weight:750; display:block; }
    a.button { display:inline-block; text-decoration:none; text-align:center; border:1px solid rgba(255,255,255,.28); background:linear-gradient(135deg,rgba(255,56,100,.22),rgba(143,92,255,.18)); color:#fff; border-radius:8px; padding:10px 12px; }
    @media (prefers-reduced-motion: reduce) { body, body::before, .panel { animation:none; } }
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
          <div class="row"><input id="color" placeholder="#b2182c or fade"><button onclick="saveTheme()">Save</button></div>
          <label>Feature</label>
          <div class="row"><input id="feature" placeholder="music"><button onclick="feature(true)">On</button><button onclick="feature(false)">Off</button></div>
        </div>
        <div class="card">
          <h2>Bot Voice</h2>
          <label>Voice channel</label>
          <select id="voiceChannels"></select>
          <div class="row"><button onclick="joinVoice()">Join VC</button><button onclick="leaveVoice()">Leave VC</button></div>
          <label>Type to talk in VC</label>
          <textarea id="ttsText" maxlength="900" placeholder="Type what the bot should say in voice..."></textarea>
          <label>Voice style</label>
          <select id="ttsVoice"><option value="alloy">Alloy</option><option value="verse">Verse</option><option value="nova">Nova</option><option value="shimmer">Shimmer</option><option value="echo">Echo</option></select>
          <button onclick="speakVoice()">Speak In VC</button>
        </div>
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
        <div class="card">
          <h2>Command Assistant</h2>
          <label>Ask about commands</label>
          <textarea id="assistantQuestion" maxlength="900" placeholder="Example: how do I set up anti nuke, make a ticket, or play music?"></textarea>
          <button onclick="askAssistant()">Ask Assistant</button>
          <div id="assistantBox"></div>
        </div>
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
        <div class="card">
          <h2>Music Controls</h2>
          <label>Song or URL</label><input id="musicQuery" placeholder="YouTube, playlist, or search">
          <div class="row"><button onclick="music('add')">Add</button><button onclick="music('play')">Play</button><button onclick="music('pause')">Pause</button><button onclick="music('resume')">Resume</button></div>
          <div class="row"><button onclick="music('skip')">Skip</button><button onclick="music('stop')">Stop</button><button onclick="music('loop')">Loop</button><button onclick="music('shuffle')">Shuffle</button></div>
          <label>Volume</label><div class="row"><input id="musicVolume" type="number" min="1" max="200" value="70"><button onclick="music('volume')">Set Volume</button></div>
          <div id="musicBox" class="card"></div>
        </div>
        <div class="card">
          <h2>Security & Backup</h2>
          <div class="row"><button onclick="backup()">Make Backup Code</button><button onclick="antinuke(true)">Anti-Nuke On</button><button onclick="antinuke(false)">Anti-Nuke Off</button></div>
          <label>Whitelist selected member/role</label>
          <div class="row"><button onclick="antiWhitelist('member')">Whitelist Member</button><button onclick="antiWhitelist('role')">Whitelist Role</button></div>
          <p id="backupBox"></p>
        </div>
        <div class="card">
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
        <div class="card">
          <h2>Live Logs</h2>
          <button onclick="loadLogs()">Refresh Logs</button>
          <div id="logsBox"></div>
        </div>
        <div class="card" id="memberTransferCard">
          <h2>Member Transfer</h2>
          <p class="notice">Only people who explicitly authorize AIN can be added. This tool never scrapes user tokens or forces anyone into a server.</p>
          <div class="row">
            <div><label>Source server</label><select id="transferSource" onchange="loadTransferStatus()"></select></div>
            <div><label>Destination server</label><select id="transferDestination" onchange="loadTransferStatus()"></select></div>
          </div>
          <div class="stats">
            <div class="stat"><b id="authorizedCount">0</b><span>authorized users</span></div>
            <div class="stat"><b id="eligibleCount">0</b><span>eligible to add</span></div>
          </div>
          <label>Authorization link for members</label>
          <div class="row"><a class="button" href="/oauth/discord/start" target="_blank" rel="noopener">Authorize with Discord</a><button onclick="copyAuthorizationLink()">Copy Authorization Link</button></div>
          <label>Admin actions</label>
          <div class="row"><button onclick="addAuthorizedMembers()">Add Authorized Members</button><button onclick="createInvite()">Create Invite</button><button id="copyInviteButton" onclick="copyInvite()" disabled>Copy Invite</button></div>
          <input id="inviteUrl" readonly placeholder="Invite link appears here">
          <div id="transferResult"></div>
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
    const transferOptions = data.guilds.map(g=>`<option value="${g.id}">${g.name}</option>`).join('');
    $('transferSource').innerHTML = transferOptions;
    $('transferDestination').innerHTML = transferOptions;
    if(data.guilds.length > 1) $('transferDestination').selectedIndex = 1;
    setStatus('Servers loaded.');
    await loadSummary();
    await loadTransferStatus();
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
  $('shopRole').innerHTML = `<option value="0">No role reward</option>` + data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
}
function renderCommands(commands){
  $('results').innerHTML = commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join('') || '<p>No commands found.</p>';
}
async function loadCommands(){ const data = await api('/api/guild/' + guild() + '/commands'); renderCommands(data.commands); }
async function search(){ const data = await api('/api/guild/' + guild() + '/search?q=' + encodeURIComponent($('query').value)); renderCommands(data.commands); }
async function askAssistant(){ const data = await api('/api/guild/' + guild() + '/assistant', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({question:$('assistantQuestion').value})}); $('assistantBox').innerHTML = `<p>${data.answer.replaceAll('\\n','<br>')}</p>` + data.commands.map(c=>`<div class="cmd"><b>${c.name}</b><span>${c.description || 'No description'}</span></div>`).join(''); setStatus('Assistant answered.'); }
async function savePrefix(){ await api('/api/guild/' + guild() + '/prefix', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({prefix:$('prefix').value})}); setStatus('Prefix saved.'); loadSummary(); }
async function saveTheme(){ await api('/api/guild/' + guild() + '/theme', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({color:$('color').value})}); setStatus('Theme saved.'); }
async function feature(enabled){ await api('/api/guild/' + guild() + '/feature', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({feature:$('feature').value, enabled})}); setStatus('Feature updated.'); }
async function joinVoice(){ await api('/api/guild/' + guild() + '/voice/join', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({channel_id:$('voiceChannels').value})}); setStatus('Bot joined the VC.'); }
async function leaveVoice(){ await api('/api/guild/' + guild() + '/voice/leave', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({})}); setStatus('Bot left the VC.'); }
async function speakVoice(){ await api('/api/guild/' + guild() + '/voice/speak', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({text:$('ttsText').value, voice:$('ttsVoice').value, channel_id:$('voiceChannels').value})}); setStatus('Bot is speaking in VC.'); $('ttsText').value=''; }
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
async function loadTransferStatus(){
  if(!$('transferSource').value || !$('transferDestination').value) return;
  try {
    const data = await api('/api/member-transfer/status?source_id=' + $('transferSource').value + '&destination_id=' + $('transferDestination').value);
    $('authorizedCount').textContent = data.authorized;
    $('eligibleCount').textContent = data.eligible;
    $('transferResult').innerHTML = data.oauth_configured ? `<p>${data.already_in_destination} authorized user(s) are already in the destination.</p>` : '<p class="notice">OAuth needs the four Discord OAuth environment settings before members can authorize.</p>';
  } catch(e){ $('transferResult').innerHTML = `<p>${e.message}</p>`; }
}
async function addAuthorizedMembers(){
  if(!confirm('Add only the eligible users who explicitly authorized AIN?')) return;
  try {
    const data = await api('/api/member-transfer/add', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({source_id:$('transferSource').value, destination_id:$('transferDestination').value})});
    $('transferResult').innerHTML = `<p><b>${data.added}</b> added · ${data.failed} failed · ${data.reauthorization_required} need to reauthorize.</p>`;
    setStatus('Authorized member transfer finished.'); await loadTransferStatus();
  } catch(e){ setStatus(e.message); }
}
async function createInvite(){
  try {
    const data = await api('/api/member-transfer/invite', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({destination_id:$('transferDestination').value})});
    $('inviteUrl').value = data.url; $('copyInviteButton').disabled = false; setStatus('24-hour invite created.');
  } catch(e){ setStatus(e.message); }
}
async function copyInvite(){ await navigator.clipboard.writeText($('inviteUrl').value); setStatus('Invite copied.'); }
async function copyAuthorizationLink(){ await navigator.clipboard.writeText(location.origin + '/oauth/discord/start'); setStatus('Authorization link copied.'); }

function setupTabs(){
  const main = document.querySelector('main.panel');
  const definitions = [
    ['overview','Overview'], ['server','Server Control'], ['ai','AI & Commands'], ['voice','Voice & Chat'],
    ['music','Music'], ['security','Security'], ['economy','Economy & Roles'], ['members','Members'], ['logs','Logs']
  ];
  const nav = document.createElement('nav'); nav.className = 'tabs'; nav.setAttribute('aria-label','Dashboard sections');
  const panels = {};
  definitions.forEach(([id,label], index)=>{
    const button = document.createElement('button'); button.className='tab-button' + (index===0?' active':''); button.textContent=label; button.type='button'; button.onclick=()=>showTab(id); nav.appendChild(button);
    const panel = document.createElement('section'); panel.className='tab-panel' + (index===0?' active':''); panel.dataset.tab=id; panels[id]=panel;
  });
  const children = [...main.children]; main.prepend(nav); definitions.forEach(([id])=>main.appendChild(panels[id]));
  children.forEach(node=>{
    const title=(node.querySelector?.('h2')?.textContent || node.id || '').toLowerCase();
    let tab='overview';
    if(title.includes('ask') || title.includes('assistant') || node.id==='results') tab='ai';
    if(title.includes('server control')) tab='server';
    if(title.includes('bot voice') || title.includes('bot chat') || title.includes('announcement')) tab='voice';
    if(title.includes('music')) tab='music';
    if(title.includes('security')) tab='security';
    if(title.includes('economy')) tab='economy';
    if(title.includes('member transfer')) tab='members';
    if(title.includes('live logs')) tab='logs';
    panels[tab].appendChild(node);
  });
  document.querySelectorAll('.grid > section.panel > .card').forEach(node=>{
    const title=(node.querySelector('h2')?.textContent || '').toLowerCase();
    let tab='overview';
    if(title.includes('bot voice') || title.includes('bot chat') || title.includes('announcement')) tab='voice';
    panels[tab].appendChild(node);
  });
}
function showTab(id){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tab===id));
  document.querySelectorAll('.tab-button').forEach(b=>b.classList.toggle('active',b.textContent===({overview:'Overview',server:'Server Control',ai:'AI & Commands',voice:'Voice & Chat',music:'Music',security:'Security',economy:'Economy & Roles',members:'Members',logs:'Logs'})[id]));
  history.replaceState(null,'','#'+id);
}
setupTabs();
if(location.hash) showTab(location.hash.slice(1));
</script>
</body>
</html>"""


class Dashboard:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.oauth_db = Path(__file__).resolve().parents[2] / "data" / "oauth_authorizations.sqlite3"
        self._init_oauth_db()

    def _init_oauth_db(self) -> None:
        self.oauth_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.oauth_db) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS oauth_authorizations (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER NOT NULL,
                    scope TEXT NOT NULL,
                    authorized_at INTEGER NOT NULL
                )"""
            )

    def _oauth_configured(self) -> bool:
        settings = self.bot.settings
        return bool(settings.discord_client_id and settings.discord_client_secret and settings.discord_oauth_redirect_uri and settings.oauth_state_secret)

    def _oauth_state(self) -> str:
        issued = str(int(time.time()))
        nonce = secrets.token_urlsafe(16)
        payload = f"{issued}.{nonce}"
        signature = hmac.new(self.bot.settings.oauth_state_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{signature}"

    def _valid_oauth_state(self, state: str) -> bool:
        try:
            issued, nonce, signature = state.split(".", 2)
            payload = f"{issued}.{nonce}"
            expected = hmac.new(self.bot.settings.oauth_state_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected) and abs(int(time.time()) - int(issued)) <= 900
        except (AttributeError, TypeError, ValueError):
            return False

    def _authorizations(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.oauth_db) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM oauth_authorizations ORDER BY authorized_at DESC")]

    async def _fresh_access_token(self, authorization: dict[str, Any]) -> str | None:
        if int(authorization["expires_at"]) > int(time.time()) + 60:
            return str(authorization["access_token"])
        refresh_token = authorization.get("refresh_token")
        if not refresh_token:
            return None
        form = {
            "client_id": self.bot.settings.discord_client_id,
            "client_secret": self.bot.settings.discord_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        async with ClientSession() as session:
            async with session.post("https://discord.com/api/v10/oauth2/token", data=form) as response:
                if response.status != 200:
                    return None
                tokens = await response.json()
        expires_at = int(time.time()) + int(tokens.get("expires_in", 0))
        with sqlite3.connect(self.oauth_db) as db:
            db.execute(
                "UPDATE oauth_authorizations SET access_token=?, refresh_token=?, expires_at=?, scope=? WHERE user_id=?",
                (tokens["access_token"], tokens.get("refresh_token") or refresh_token, expires_at, tokens.get("scope", "identify guilds.join"), authorization["user_id"]),
            )
        return str(tokens["access_token"])

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

    async def oauth_start(self, _: web.Request) -> web.Response:
        if not self._oauth_configured():
            raise web.HTTPServiceUnavailable(text="Discord OAuth is not configured yet.")
        query = urllib.parse.urlencode({
            "client_id": self.bot.settings.discord_client_id,
            "redirect_uri": self.bot.settings.discord_oauth_redirect_uri,
            "response_type": "code",
            "scope": "identify guilds.join",
            "state": self._oauth_state(),
            "prompt": "consent",
        })
        raise web.HTTPFound(f"https://discord.com/oauth2/authorize?{query}")

    async def oauth_callback(self, request: web.Request) -> web.Response:
        if not self._oauth_configured() or not self._valid_oauth_state(request.query.get("state", "")):
            raise web.HTTPBadRequest(text="Invalid or expired authorization request.")
        code = request.query.get("code")
        if not code:
            raise web.HTTPBadRequest(text="Discord authorization was cancelled or no code was returned.")
        form = {
            "client_id": self.bot.settings.discord_client_id,
            "client_secret": self.bot.settings.discord_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.bot.settings.discord_oauth_redirect_uri,
        }
        async with ClientSession() as session:
            async with session.post("https://discord.com/api/v10/oauth2/token", data=form) as response:
                tokens = await response.json()
                if response.status != 200:
                    raise web.HTTPBadRequest(text="Discord could not complete authorization.")
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as response:
                user = await response.json()
                if response.status != 200:
                    raise web.HTTPBadRequest(text="Discord could not identify the authorized user.")
        expires_at = int(time.time()) + int(tokens.get("expires_in", 0))
        username = user.get("global_name") or user.get("username") or user["id"]
        with sqlite3.connect(self.oauth_db) as db:
            db.execute(
                """INSERT INTO oauth_authorizations
                   (user_id, username, access_token, refresh_token, expires_at, scope, authorized_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
                   access_token=excluded.access_token, refresh_token=excluded.refresh_token,
                   expires_at=excluded.expires_at, scope=excluded.scope, authorized_at=excluded.authorized_at""",
                (str(user["id"]), str(username), tokens["access_token"], tokens.get("refresh_token"), expires_at, tokens.get("scope", "identify guilds.join"), int(time.time())),
            )
        return web.Response(
            text="<!doctype html><meta charset='utf-8'><title>AIN authorized</title><body style='font-family:system-ui;background:#09070d;color:#fff;padding:3rem'><h1>Authorization complete</h1><p>You explicitly authorized AIN to add your Discord account to a server when an AIN administrator starts a transfer. You can close this window.</p></body>",
            content_type="text/html",
        )

    async def transfer_status(self, request: web.Request) -> web.Response:
        self.require_token(request)
        source = self.guild_or_404(request.query.get("source_id", "0"))
        destination = self.guild_or_404(request.query.get("destination_id", "0"))
        authorized = self._authorizations()
        eligible = [row for row in authorized if source.get_member(int(row["user_id"])) and not destination.get_member(int(row["user_id"]))]
        return web.json_response({
            "authorized": len(authorized),
            "eligible": len(eligible),
            "already_in_destination": sum(1 for row in authorized if destination.get_member(int(row["user_id"]))),
            "oauth_configured": self._oauth_configured(),
        })

    async def transfer_members(self, request: web.Request) -> web.Response:
        self.require_token(request)
        body = await request.json()
        source = self.guild_or_404(str(body.get("source_id", "0")))
        destination = self.guild_or_404(str(body.get("destination_id", "0")))
        if source.id == destination.id:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Choose two different servers."}), content_type="application/json")
        if destination.me is None or not destination.me.guild_permissions.manage_guild:
            raise web.HTTPForbidden(text=json.dumps({"error": "The bot needs Manage Server in the destination server."}), content_type="application/json")
        eligible = [row for row in self._authorizations() if source.get_member(int(row["user_id"])) and not destination.get_member(int(row["user_id"]))]
        added = failed = expired = 0
        async with ClientSession() as session:
            for authorization in eligible:
                access_token = await self._fresh_access_token(authorization)
                if not access_token:
                    expired += 1
                    continue
                url = f"https://discord.com/api/v10/guilds/{destination.id}/members/{authorization['user_id']}"
                headers = {"Authorization": f"Bot {self.bot.settings.discord_token}", "Content-Type": "application/json"}
                async with session.put(url, headers=headers, json={"access_token": access_token}) as response:
                    if response.status in {201, 204}:
                        added += 1
                    else:
                        failed += 1
        return web.json_response({"eligible": len(eligible), "added": added, "failed": failed, "reauthorization_required": expired})

    async def create_transfer_invite(self, request: web.Request) -> web.Response:
        self.require_token(request)
        body = await request.json()
        destination = self.guild_or_404(str(body.get("destination_id", "0")))
        channel = next((c for c in destination.text_channels if c.permissions_for(destination.me).create_instant_invite), None) if destination.me else None
        if channel is None:
            raise web.HTTPForbidden(text=json.dumps({"error": "The bot needs Create Invite in a destination text channel."}), content_type="application/json")
        invite = await channel.create_invite(max_age=86400, max_uses=0, unique=True, reason="AIN dashboard member transfer fallback")
        return web.json_response({"url": invite.url, "expires_in": 86400})

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

    async def make_tts_file(self, text: str, voice: str) -> Path:
        api_key = getattr(self.bot.settings, "openai_api_key", None)
        if not api_key:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Add OPENAI_API_KEY with credits to use type-to-talk."}), content_type="application/json")
        safe_voice = voice if voice in {"alloy", "verse", "nova", "shimmer", "echo"} else "alloy"
        path = Path(tempfile.gettempdir()) / f"ainbot-tts-{discord.utils.utcnow().timestamp()}.mp3"
        payload = {"model": os.getenv("OPENAI_TTS_MODEL", "tts-1"), "voice": safe_voice, "input": text[:900]}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with ClientSession() as session:
            async with session.post("https://api.openai.com/v1/audio/speech", headers=headers, json=payload) as response:
                if response.status >= 400:
                    detail = await response.text()
                    raise web.HTTPBadRequest(text=json.dumps({"error": f"TTS failed: {detail[:300]}"}), content_type="application/json")
                path.write_bytes(await response.read())
        return path

    async def speak_voice(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Type something for the bot to say."}), content_type="application/json")
        current = guild.voice_client
        if current is None or not current.is_connected():
            channel = guild.get_channel(int(body.get("channel_id", 0) or 0))
            if not isinstance(channel, discord.VoiceChannel):
                raise web.HTTPBadRequest(text=json.dumps({"error": "Bot is not in VC. Pick a voice channel first."}), content_type="application/json")
            current = await channel.connect(self_deaf=False)
        if current.is_playing():
            current.stop()
        audio_path = await self.make_tts_file(text, str(body.get("voice", "alloy")))

        def cleanup(_: Exception | None = None, path: Path = audio_path) -> None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        source = discord.FFmpegPCMAudio(str(audio_path), executable=ffmpeg_executable())
        current.play(source, after=cleanup)
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
    dashboard = Dashboard(bot)
    app = web.Application()
    app.router.add_get("/", dashboard.index)
    app.router.add_get("/oauth/discord/start", dashboard.oauth_start)
    app.router.add_get("/oauth/discord/callback", dashboard.oauth_callback)
    app.router.add_get("/api/guilds", dashboard.guilds)
    app.router.add_get("/api/member-transfer/status", dashboard.transfer_status)
    app.router.add_post("/api/member-transfer/add", dashboard.transfer_members)
    app.router.add_post("/api/member-transfer/invite", dashboard.create_transfer_invite)
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
