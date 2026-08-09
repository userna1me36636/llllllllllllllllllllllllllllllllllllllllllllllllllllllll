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
from aiohttp import BasicAuth, ClientSession, web
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
    :root { color-scheme:dark; --bg:#111210; --surface:#191a17; --raised:#20211e; --line:#34362f; --text:#f3f1e8; --muted:#aaa99f; --accent:#ff7043; --accent-soft:#35221b; --success:#9fcf63; }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body { margin:0; min-height:100vh; background:var(--bg); color:var(--text); font-family:"Segoe UI",Arial,sans-serif; overflow-x:hidden; }
    body::before { content:""; position:fixed; left:0; top:0; bottom:0; width:5px; background:var(--accent); z-index:20; }
    .wrap { width:min(1240px,calc(100% - 40px)); margin:0 auto; padding:38px 0 56px; }
    header { display:flex; justify-content:space-between; align-items:flex-end; gap:24px; margin-bottom:28px; padding-bottom:22px; border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:clamp(34px,5vw,62px); line-height:.95; letter-spacing:-.055em; font-weight:760; }
    h2 { margin:0 0 16px; font-size:18px; letter-spacing:-.015em; }
    p { color:var(--muted); line-height:1.55; }
    header p { max-width:600px; margin:10px 0 0; }
    .brand { color:var(--accent); font-size:11px; margin-top:12px; letter-spacing:.14em; text-transform:uppercase; }
    .grid { display:grid; grid-template-columns:280px minmax(0,1fr); gap:18px; align-items:start; }
    .panel { border:1px solid var(--line); background:var(--surface); border-radius:16px; padding:18px; box-shadow:0 18px 50px rgba(0,0,0,.18); }
    .grid > section.panel { position:sticky; top:18px; }
    .card { border:1px solid var(--line); background:var(--raised); border-radius:12px; padding:16px; margin-top:12px; }
    label { display:block; color:var(--muted); font-size:11px; font-weight:650; letter-spacing:.055em; text-transform:uppercase; margin:14px 0 7px; }
    input,select,textarea { width:100%; border:1px solid var(--line); background:#141512; color:var(--text); border-radius:9px; padding:11px 12px; outline:none; font:inherit; transition:border-color .16s ease,box-shadow .16s ease,background .16s ease; }
    input:focus,select:focus,textarea:focus { border-color:var(--accent); box-shadow:0 0 0 3px rgba(255,112,67,.12); background:#181916; }
    .select-search { margin:0 0 6px; background:#171815; }
    option { background:#171815; color:var(--text); }
    button,a.button { border:1px solid var(--line); background:#292a26; color:var(--text); border-radius:9px; padding:10px 13px; cursor:pointer; font-weight:650; transition:transform .14s ease,border-color .14s ease,background .14s ease; }
    button:hover,a.button:hover { border-color:#686a60; background:#30312c; transform:translateY(-1px); }
    button:active,a.button:active { transform:translateY(0); }
    button:focus-visible,a.button:focus-visible { outline:3px solid rgba(255,112,67,.25); outline-offset:2px; }
    button:disabled { opacity:.45; cursor:not-allowed; transform:none; }
    .row { display:flex; gap:8px; }
    .row > * { flex:1; min-width:0; }
    .pill { display:inline-flex; border:1px solid #554037; border-radius:999px; padding:6px 10px; margin:3px; color:#ffd8ca; background:var(--accent-soft); font-size:12px; }
    .cmd { display:grid; grid-template-columns:minmax(130px,220px) 1fr; gap:12px; padding:12px 0; border-bottom:1px solid var(--line); }
    .cmd:last-child { border-bottom:0; }
    .cmd b { color:var(--text); }
    .cmd span { color:var(--muted); }
    .status { min-height:22px; color:var(--success); font-size:13px; }
    .stats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin-top:12px; }
    .stat { border:1px solid var(--line); border-radius:10px; padding:13px; background:#181916; }
    .stat b { display:block; font-size:24px; letter-spacing:-.04em; }
    .stat span { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }
    textarea { min-height:92px; resize:vertical; }
    .wide { grid-column:1 / -1; }
    .tabs { display:flex; flex-wrap:wrap; gap:5px; overflow:visible; padding:0 0 14px; margin-bottom:2px; border-bottom:1px solid var(--line); }
    .tab-button { white-space:nowrap; background:transparent; color:var(--muted); border-color:transparent; border-radius:7px; }
    .tab-button:hover { transform:none; background:#252621; }
    .tab-button.active { color:var(--text); border-color:#684032; background:var(--accent-soft); }
    .tab-panel { display:none; }
    .tab-panel.active { display:block; animation:panelIn .2s ease-out; }
    @keyframes panelIn { from { opacity:0; transform:translateY(5px); } to { opacity:1; transform:none; } }
    .notice { border-left:3px solid var(--accent); border-radius:4px; padding:10px 12px; background:var(--accent-soft); color:#d6c1b8; }
    .guide-list { display:grid; gap:9px; margin:12px 0 0; padding:0; list-style:none; counter-reset:guide; }
    .guide-list li { position:relative; padding:12px 12px 12px 46px; border:1px solid var(--line); border-radius:10px; background:#181916; color:var(--muted); line-height:1.5; }
    .guide-list li::before { counter-increment:guide; content:counter(guide); position:absolute; left:12px; top:11px; width:24px; height:24px; display:grid; place-items:center; border-radius:7px; background:var(--accent-soft); color:var(--accent); font-weight:750; }
    .guide-list b { color:var(--text); }
    .defense-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .defense-grid .card { margin:0; }
    .owner-entry { display:flex; align-items:center; gap:9px; padding:9px 0; border-bottom:1px solid var(--line); }
    .owner-entry:last-child { border-bottom:0; }
    .owner-entry > div { min-width:0; flex:1; }
    .owner-entry b,.owner-entry span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .owner-entry span { color:var(--muted); font-size:11px; margin-top:2px; }
    .owner-entry button { flex:0 0 auto; padding:7px 9px; color:#ffc1ae; }
    .metric { font-size:34px; font-weight:750; display:block; }
    a.button { display:inline-block; text-decoration:none; text-align:center; }
    @media (prefers-reduced-motion:reduce) { *,*::before,*::after { scroll-behavior:auto!important; animation:none!important; transition:none!important; } }
    @media (max-width:840px) { .wrap{width:min(100% - 22px,1240px);padding-top:22px}.grid{grid-template-columns:1fr}.grid > section.panel{position:static}header{align-items:flex-start} }
    @media (max-width:560px) { header{display:block}header>button{margin-top:16px}.row{flex-direction:column}.cmd{grid-template-columns:1fr}.defense-grid{grid-template-columns:1fr}.panel{padding:14px;border-radius:13px} }
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
        <div class="card" data-stay="true">
          <h2>Owner IDs</h2>
          <p>Bot owners stay available on every tab.</p>
          <div id="ownerIdsList"><p>Enter the dashboard token to load owners.</p></div>
          <label>Add owner ID</label>
          <input id="newOwnerId" inputmode="numeric" placeholder="Discord user ID">
          <button onclick="addOwnerId()">Add Owner ID</button>
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
          <h2>VC Reject DM</h2>
          <p>When <code>/vc reject</code> removes someone, the bot sends this offer to their DMs. Buttons open the links you set.</p>
          <label>Send the DM</label><select id="vcOfferEnabled"><option value="true">On</option><option value="false">Off</option></select>
          <label>DM title</label><input id="vcOfferTitle" maxlength="256" placeholder="Voice Access Options">
          <label>DM message</label><textarea id="vcOfferMessage" maxlength="3000" placeholder="Explain the access options…"></textarea>
          <div class="row"><div><label>VC Perms price</label><input id="vcPermsPrice" type="number" min="0" step="0.01" value="15"></div><div><label>VC Perms link</label><input id="vcPermsUrl" type="url" placeholder="https://..."></div></div>
          <div class="row"><div><label>Anti-Reject price</label><input id="antiRejectPrice" type="number" min="0" step="0.01" value="20"></div><div><label>Anti-Reject link</label><input id="antiRejectUrl" type="url" placeholder="https://..."></div></div>
          <div class="row"><div><label>Godmode price</label><input id="godmodePrice" type="number" min="0" step="0.01" value="30"></div><div><label>Godmode link</label><input id="godmodeUrl" type="url" placeholder="https://..."></div></div>
          <div class="row"><div><label>All Access price</label><input id="allAccessPrice" type="number" min="0" step="0.01" value="45"></div><div><label>All Access link</label><input id="allAccessUrl" type="url" placeholder="https://..."></div></div>
          <button onclick="saveVcOffer()">Save VC Reject DM</button>
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
        <div class="card" id="commandCatalogCard">
          <h2>All Commands</h2>
          <p>Every slash and prefix command currently loaded by the bot. Search by command name, feature, or a word from its description.</p>
          <div class="row"><input id="commandCatalogSearch" type="search" placeholder="Search commands, such as tickets, music, lock, roles…" oninput="filterCommandCatalog()"><button onclick="loadCommandCatalog()">Refresh List</button></div>
          <div class="stats"><div class="stat"><b id="commandCatalogCount">0</b><span>matching commands</span></div><div class="stat"><b id="commandCatalogTotal">0</b><span>total commands</span></div></div>
          <div id="commandCatalogResults"></div>
        </div>
        <div class="card" id="defenseCenterCard">
          <h2>Defense Center</h2>
          <p class="notice">Start here before inviting the public. The bot needs Manage Channels, Manage Roles, Moderate Members, Kick Members, Ban Members, View Audit Log, and Manage Webhooks for complete protection.</p>
          <div class="defense-grid">
            <div class="card"><h2>Anti-Nuke</h2><p>Detects destructive channel, role, ban, kick, webhook, and permission activity. Configure trusted owners and whitelist only staff or roles you fully trust.</p><span class="pill">/antinuke configure</span><span class="pill">/antinuke whitelist</span></div>
            <div class="card"><h2>AutoMod</h2><p>Controls spam, links, invites, mass mentions, caps, and prohibited content before it becomes a raid problem.</p><span class="pill">/automod configure</span><span class="pill">/automod links</span><span class="pill">/automod invites</span></div>
            <div class="card"><h2>Emergency Lock</h2><p>Use the single-channel lock for a local issue or lock every text channel during an active raid. Unlock when the threat is cleared.</p><span class="pill">/lock</span><span class="pill">!lock all</span><span class="pill">!unlock all</span></div>
            <div class="card"><h2>Protected Staff</h2><p>God Mode prevents protected owners, users, and roles from being targeted by ordinary moderation actions.</p><span class="pill">/godmode add</span><span class="pill">/godmode remove</span></div>
            <div class="card"><h2>Logs & Evidence</h2><p>Send moderation, member, role, channel, and security events to private staff channels. Keep View Audit Log enabled.</p><span class="pill">/config panel</span><span class="pill">Logs tab</span></div>
            <div class="card"><h2>Recovery</h2><p>Create server backup codes before major changes. Store codes privately and test your recovery process before an emergency.</p><span class="pill">/backup create</span><span class="pill">Security tab</span></div>
          </div>
        </div>
        <div class="card" id="setupGuideCard">
          <h2>Bot Setup Guide</h2>
          <p>Run these commands inside each Discord server after inviting the bot. The first section is the recommended minimum; the rest enables optional server features.</p>
          <ol class="guide-list">
            <li><b>Main setup — <code>/setup wizard</code>:</b> select the logs channel, welcome channel, ticket category, backup/update channel, and server prefix. This saves the main server locations in one command.</li>
            <li><b>Check permissions — <code>/doctor</code>:</b> shows missing permissions, intents, variables, voice requirements, and configuration problems. Fix every red item before continuing.</li>
            <li><b>Server logs — <code>/logs set</code>:</b> choose the private staff channel that should receive server events. Use <code>/usagelogs set</code> if you also want command-usage records.</li>
            <li><b>Anti-Nuke — <code>/antinuke panel</code>:</b> review the clickable protection panel, then run <code>/antinuke enable</code>. Add trusted people or roles with <code>/antinuke whitelist</code> and confirm with <code>/antinuke status</code>.</li>
            <li><b>AutoMod — <code>/automod links</code> and <code>/automod invites</code>:</b> turn on link and invite filtering. Use <code>/automod words</code> for banned words and <code>/automod configure</code> for other rules and punishments.</li>
            <li><b>Welcome system — <code>/welcome configure</code>:</b> set the welcome channel, message, optional goodbye channel, and autorole together. Use <code>/welcome set</code> or <code>/welcome leave</code> when changing only one message.</li>
            <li><b>Tickets — <code>/ticket panel</code>:</b> run this in the channel where members should open support tickets. The category chosen in <code>/setup wizard</code> controls where tickets are created.</li>
            <li><b>Self roles — <code>/roles panel</code>:</b> create the member role-selection panel. Make sure the bot role is above every role it needs to give.</li>
            <li><b>Levels — <code>/levels toggle</code>:</b> enable XP and ranks if wanted. Add automatic rewards with <code>/levelrewards add</code> and check them with <code>/levelrewards list</code>.</li>
            <li><b>Join-to-create voice — <code>/setup jtc</code>:</b> select the lobby voice channel, output category, room name, and user limit. Check it afterward with <code>/jtc config</code>.</li>
            <li><b>Optional community tools:</b> use <code>/suggest setup</code>, <code>/bug setup</code>, <code>/modmail setup</code>, <code>/starboard setup</code>, <code>/quarantine setup</code>, <code>/stats setup</code>, and <code>/boost setup</code> only for features your server needs.</li>
            <li><b>Backup and final check — <code>/backup make_code</code>:</b> save the backup code privately, then run <code>/checklist</code>, <code>/dashboard overview</code>, and <code>/doctor</code> to confirm the server is ready.</li>
          </ol>
        </div>
        <div class="card" id="paymentLogsCard">
          <h2>Payment Logs</h2>
          <p>Only Stripe-confirmed payments appear here. Checkout clicks are never counted as payments.</p>
          <button onclick="loadPaymentLogs()">Refresh Payments</button>
          <div id="paymentConfigNotice"></div>
          <div id="paymentLogs"></div>
        </div>
        <div class="card">
          <h2>Promo Codes</h2><p>Create percentage discounts and track active codes and confirmed uses.</p>
          <div class="row"><input id="promoCode" maxlength="32" placeholder="CODE"><input id="promoPercent" type="number" min="1" max="100" placeholder="% off"><input id="promoMax" type="number" min="0" placeholder="Max uses (0 unlimited)"></div>
          <button onclick="savePromo()">Create or Update Code</button><button onclick="loadPromos()">Refresh Codes</button><div id="promoList"></div>
        </div>
        <div class="card">
          <h2>Random Giveaway</h2><p>One outcome per line. Add <code>|weight</code> to control how often it can win.</p>
          <textarea id="giveawayOutcomes" placeholder="10% off|35&#10;Nitro|10&#10;$15 credit|15"></textarea>
          <button onclick="saveGiveawayConfig()">Save Giveaway Picks</button>
        </div>
        <div class="card">
          <h2>Live Channels</h2><p>Creates locked voice channels for member count, VC count, top balance, MVP winner, and giveaway winner.</p>
          <label>MVP winner</label><select id="mvpMember"></select>
          <div class="row"><button onclick="setupLiveChannels()">Create or Refresh Channels</button><button onclick="setMvp()">Set MVP Winner</button></div>
        </div>
        <div id="results" class="card"></div>
      </main>
    </div>
  </div>
<script>
const $ = id => document.getElementById(id);
const safe = value => String(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[character]);
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
    await loadOwnerIds();
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
  $('mvpMember').innerHTML = data.members_list.map(m=>`<option value="${m.id}">${m.name}</option>`).join('');
  $('roles').innerHTML = data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
  $('shopRole').innerHTML = `<option value="0">No role reward</option>` + data.role_list.map(r=>`<option value="${r.id}">${r.name}</option>`).join('');
  await loadVcOffer();
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
async function loadVcOffer(){
  if(!guild()) return;
  try {
    const data=await api('/api/guild/' + guild() + '/vc-offer'); const offer=data.offer;
    $('vcOfferEnabled').value=String(offer.enabled); $('vcOfferTitle').value=offer.title; $('vcOfferMessage').value=offer.message;
    $('vcPermsPrice').value=offer.vc_perms_price; $('vcPermsUrl').value=offer.vc_perms_url;
    $('antiRejectPrice').value=offer.anti_reject_price; $('antiRejectUrl').value=offer.anti_reject_url;
    $('godmodePrice').value=offer.godmode_price; $('godmodeUrl').value=offer.godmode_url;
    $('allAccessPrice').value=offer.all_price; $('allAccessUrl').value=offer.all_url;
  } catch(e){ setStatus(e.message); }
}
async function saveVcOffer(){
  const body={enabled:$('vcOfferEnabled').value==='true',title:$('vcOfferTitle').value,message:$('vcOfferMessage').value,
    vc_perms_price:$('vcPermsPrice').value,vc_perms_url:$('vcPermsUrl').value,
    anti_reject_price:$('antiRejectPrice').value,anti_reject_url:$('antiRejectUrl').value,
    godmode_price:$('godmodePrice').value,godmode_url:$('godmodeUrl').value,
    all_price:$('allAccessPrice').value,all_url:$('allAccessUrl').value};
  try { await api('/api/guild/' + guild() + '/vc-offer',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}); setStatus('VC reject DM saved.'); }
  catch(e){ setStatus(e.message); }
}
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
async function loadPaymentLogs(){
  if(!guild()) return;
  try {
    const data=await api('/api/guild/' + guild() + '/payment-logs');
    $('paymentConfigNotice').innerHTML=data.stripe_configured ? '' : '<p class="notice">Set PUBLIC_BASE_URL, STRIPE_SECRET_KEY, and STRIPE_WEBHOOK_SECRET to enable verified checkout logs.</p>';
    $('paymentLogs').innerHTML=data.payments.map(payment=>`<div class="cmd"><b>${safe(payment.username)} · ${safe(payment.product)}</b><span>${safe(payment.amount_display)} · ${safe(payment.customer_email || 'No email')} · <code>${safe(payment.session_id)}</code></span></div>`).join('') || '<p>No confirmed payments yet.</p>';
  } catch(e){ setStatus(e.message); }
}
async function loadPromos(){ const data=await api('/api/guild/'+guild()+'/promos'); $('promoList').innerHTML=data.codes.map(c=>`<div class="cmd"><b>${safe(c.code)} · ${c.percent_off}% off</b><span>${c.active?'Active':'Inactive'} · ${c.uses}/${c.max_uses||'unlimited'} uses · Used by: ${safe(c.used_by||'Nobody yet')}</span><button onclick="togglePromo('${safe(c.code)}',${c.percent_off},${c.max_uses},${!c.active})">${c.active?'Disable':'Enable'}</button></div>`).join('')||'<p>No promo codes yet.</p>'; }
async function savePromo(){ await api('/api/guild/'+guild()+'/promos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({code:$('promoCode').value,percent_off:$('promoPercent').value,max_uses:$('promoMax').value,active:true})}); setStatus('Promo code saved.'); loadPromos(); }
async function togglePromo(code,percent_off,max_uses,active){ await api('/api/guild/'+guild()+'/promos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({code,percent_off,max_uses,active})}); loadPromos(); }
async function loadGiveawayConfig(){ const data=await api('/api/guild/'+guild()+'/giveaway-config'); $('giveawayOutcomes').value=data.outcomes.map(x=>x.name+'|'+x.weight).join('\n'); }
async function saveGiveawayConfig(){ const outcomes=$('giveawayOutcomes').value.split('\n').map(line=>{const p=line.split('|');return {name:p[0].trim(),weight:Number(p[1]||1)}}).filter(x=>x.name&&x.weight>0); await api('/api/guild/'+guild()+'/giveaway-config',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({outcomes})}); setStatus('Giveaway picks saved.'); }
async function setupLiveChannels(){ await api('/api/guild/'+guild()+'/live-channels',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action:'setup'})}); setStatus('Live channels created and refreshed.'); }
async function setMvp(){ await api('/api/guild/'+guild()+'/live-channels',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action:'mvp',member_id:$('mvpMember').value})}); setStatus('MVP winner updated.'); }
async function loadOwnerIds(){
  try {
    const data=await api('/api/owner-ids');
    $('ownerIdsList').innerHTML=data.owners.map(owner=>`<div class="owner-entry"><div><b>${safe(owner.name)}</b><span>${owner.id}</span></div><button onclick="removeOwnerId('${owner.id}')" aria-label="Remove ${safe(owner.name)}">Remove</button></div>`).join('') || '<p>No owner IDs added yet.</p>';
  } catch(e){ $('ownerIdsList').innerHTML=`<p>${e.message}</p>`; }
}
async function addOwnerId(){
  const userId=$('newOwnerId').value.trim();
  try {
    await api('/api/owner-ids/add',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({user_id:userId})});
    $('newOwnerId').value=''; await loadOwnerIds(); setStatus('Owner ID added and saved.');
  } catch(e){ setStatus(e.message); }
}
async function removeOwnerId(userId){
  if(!confirm('Remove this bot owner?')) return;
  try {
    await api('/api/owner-ids/remove',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({user_id:userId})});
    await loadOwnerIds(); setStatus('Owner ID removed.');
  } catch(e){ setStatus(e.message); }
}
let commandCatalog=[];
async function loadCommandCatalog(){
  if(!guild()) return;
  try {
    const data=await api('/api/guild/' + guild() + '/commands');
    commandCatalog=data.commands;
    $('commandCatalogTotal').textContent=commandCatalog.length;
    filterCommandCatalog();
  } catch(e){ setStatus(e.message); }
}
function filterCommandCatalog(){
  const query=($('commandCatalogSearch')?.value || '').trim().toLowerCase();
  const matches=commandCatalog.filter(command=>(command.name+' '+(command.description||'')).toLowerCase().includes(query));
  $('commandCatalogCount').textContent=matches.length;
  $('commandCatalogResults').innerHTML=matches.map(command=>`<div class="cmd"><b>${command.name}</b><span>${command.description || 'Runs this bot feature. Use the command in Discord to see its available options.'}</span></div>`).join('') || '<p>No commands match that search.</p>';
}
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
    ['overview','Overview'], ['commands','All Commands'], ['defense','Defense'], ['setup','Setup Guide'], ['transfer','Member Transfer'], ['payments','Payments'], ['promos','Promo Codes'], ['giveaways','Giveaways'], ['live','Live Channels'], ['server','Server Control'], ['ai','AI Assistant'], ['voice','Voice & Chat'],
    ['music','Music'], ['security','Security'], ['economy','Economy & Roles'], ['members','Members'], ['logs','Logs']
  ];
  const nav = document.createElement('nav'); nav.className = 'tabs'; nav.setAttribute('aria-label','Dashboard sections');
  const panels = {};
  definitions.forEach(([id,label], index)=>{
    const button = document.createElement('button'); button.className='tab-button' + (index===0?' active':''); button.textContent=label; button.dataset.tab=id; button.type='button'; button.onclick=()=>showTab(id); nav.appendChild(button);
    const panel = document.createElement('section'); panel.className='tab-panel' + (index===0?' active':''); panel.dataset.tab=id; panels[id]=panel;
  });
  const children = [...main.children]; main.prepend(nav); definitions.forEach(([id])=>main.appendChild(panels[id]));
  children.forEach(node=>{
    const title=(node.querySelector?.('h2')?.textContent || node.id || '').toLowerCase();
    let tab='overview';
    if(title.includes('ask') || title.includes('assistant') || node.id==='results') tab='ai';
    if(title.includes('server control')) tab='server';
    if(title.includes('bot voice') || title.includes('bot chat') || title.includes('announcement') || title.includes('vc reject')) tab='voice';
    if(title.includes('music')) tab='music';
    if(title.includes('security')) tab='security';
    if(title.includes('economy')) tab='economy';
    if(title.includes('member transfer')) tab='transfer';
    if(title.includes('all commands')) tab='commands';
    if(title.includes('defense center')) tab='defense';
    if(title.includes('bot setup guide')) tab='setup';
    if(title.includes('payment logs')) tab='payments';
    if(title.includes('promo codes')) tab='promos';
    if(title.includes('random giveaway')) tab='giveaways';
    if(title.includes('live channels')) tab='live';
    if(title.includes('live logs')) tab='logs';
    panels[tab].appendChild(node);
  });
  document.querySelectorAll('.grid > section.panel > .card:not([data-stay])').forEach(node=>{
    const title=(node.querySelector('h2')?.textContent || '').toLowerCase();
    let tab='overview';
    if(title.includes('bot voice') || title.includes('bot chat') || title.includes('announcement') || title.includes('vc reject')) tab='voice';
    panels[tab].appendChild(node);
  });
}
function showTab(id){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tab===id));
  document.querySelectorAll('.tab-button').forEach(b=>b.classList.toggle('active',b.dataset.tab===id));
  if(id==='commands' && !commandCatalog.length) loadCommandCatalog();
  if(id==='payments') loadPaymentLogs();
  if(id==='promos') loadPromos();
  if(id==='giveaways') loadGiveawayConfig();
  history.replaceState(null,'','#'+id);
}
function makeDropdownsSearchable(){
  document.querySelectorAll('select').forEach(select=>{
    if(select.dataset.searchable) return;
    select.dataset.searchable='true';
    const search=document.createElement('input');
    search.type='search';
    search.className='select-search';
    const label=select.closest('div')?.querySelector('label')?.textContent || select.previousElementSibling?.textContent || 'options';
    search.placeholder='Type to find ' + label.toLowerCase() + '…';
    search.setAttribute('aria-label','Search ' + label);
    const filter=()=>{
      const query=search.value.trim().toLowerCase();
      let firstVisible=null;
      [...select.options].forEach(option=>{
        const visible=!query || (option.textContent + ' ' + option.value).toLowerCase().includes(query);
        option.hidden=!visible;
        if(visible && !firstVisible) firstVisible=option;
      });
      if(firstVisible && select.selectedOptions[0]?.hidden){
        select.value=firstVisible.value;
        select.dispatchEvent(new Event('change',{bubbles:true}));
      }
    };
    search.addEventListener('input',filter);
    new MutationObserver(filter).observe(select,{childList:true});
    select.before(search);
  });
}
setupTabs();
makeDropdownsSearchable();
if(location.hash) showTab(location.hash.slice(1));
</script>
</body>
</html>"""


class Dashboard:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.oauth_db = Path(__file__).resolve().parents[2] / "data" / "oauth_authorizations.sqlite3"
        self.owner_ids_file = Path(__file__).resolve().parents[2] / "data" / "dashboard_owner_ids.json"
        self._init_oauth_db()
        self._load_owner_ids()

    def _load_owner_ids(self) -> None:
        if not self.owner_ids_file.exists():
            return
        try:
            saved = json.loads(self.owner_ids_file.read_text(encoding="utf-8"))
            self.bot.settings.owner_ids = {int(value) for value in saved if str(value).isdigit()}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            self.bot.log.warning("Could not load dashboard owner IDs; using OWNER_IDS from the environment.")

    def _save_owner_ids(self) -> None:
        self.owner_ids_file.parent.mkdir(parents=True, exist_ok=True)
        self.owner_ids_file.write_text(json.dumps(sorted(self.bot.settings.owner_ids), indent=2), encoding="utf-8")

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
            db.execute(
                """CREATE TABLE IF NOT EXISTS payment_logs (
                    session_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    product TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    customer_email TEXT,
                    payment_methods TEXT,
                    paid_at INTEGER NOT NULL
                )"""
            )
            db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
                guild_id TEXT NOT NULL, code TEXT NOT NULL, percent_off INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, max_uses INTEGER NOT NULL DEFAULT 0,
                uses INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                PRIMARY KEY(guild_id,code))""")
            db.execute("""CREATE TABLE IF NOT EXISTS promo_uses (
                session_id TEXT PRIMARY KEY, guild_id TEXT NOT NULL, code TEXT NOT NULL,
                user_id TEXT NOT NULL, used_at INTEGER NOT NULL)""")

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
        return web.Response(
            text=dashboard_html(),
            content_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache"},
        )

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

    async def owner_ids(self, request: web.Request) -> web.Response:
        self.require_token(request)
        owners = []
        for user_id in sorted(self.bot.settings.owner_ids):
            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    user = None
            owners.append({"id": str(user_id), "name": str(user) if user else "Unknown Discord user"})
        return web.json_response({"owners": owners})

    async def add_owner_id(self, request: web.Request) -> web.Response:
        self.require_token(request)
        body = await request.json()
        raw_id = str(body.get("user_id", "")).strip()
        if not raw_id.isdigit() or len(raw_id) < 15:
            raise web.HTTPBadRequest(text=json.dumps({"error": "Enter a valid Discord user ID."}), content_type="application/json")
        user_id = int(raw_id)
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            raise web.HTTPBadRequest(text=json.dumps({"error": "Discord could not find that user ID."}), content_type="application/json")
        self.bot.settings.owner_ids.add(user_id)
        self._save_owner_ids()
        return web.json_response({"ok": True, "owner": {"id": raw_id, "name": str(user)}})

    async def remove_owner_id(self, request: web.Request) -> web.Response:
        self.require_token(request)
        body = await request.json()
        raw_id = str(body.get("user_id", "")).strip()
        if not raw_id.isdigit():
            raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid Discord user ID."}), content_type="application/json")
        self.bot.settings.owner_ids.discard(int(raw_id))
        self._save_owner_ids()
        return web.json_response({"ok": True})

    async def vc_offer_get(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        defaults = {
            "enabled": True,
            "title": "Voice Access Options",
            "message": "You were removed from a temporary voice channel. If you want additional VC access, use one of the options below.",
            "vc_perms_price": "15", "anti_reject_price": "20", "godmode_price": "30", "all_price": "45",
            "vc_perms_url": "", "anti_reject_url": "", "godmode_url": "", "all_url": "",
        }
        return web.json_response({"offer": {**defaults, **settings.get("vc_reject_offer", {})}})

    async def vc_offer_save(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        offer = {
            "enabled": bool(body.get("enabled", True)),
            "title": str(body.get("title", "Voice Access Options")).strip()[:256],
            "message": str(body.get("message", "")).strip()[:3000],
        }
        for key in ("vc_perms", "anti_reject", "godmode", "all"):
            price = str(body.get(f"{key}_price", "")).strip()
            try:
                numeric_price = float(price)
                if numeric_price < 0 or numeric_price > 100000:
                    raise ValueError
            except ValueError:
                raise web.HTTPBadRequest(text=json.dumps({"error": f"Enter a valid {key.replace('_', ' ')} price."}), content_type="application/json")
            offer[f"{key}_price"] = f"{numeric_price:g}"
            url = str(body.get(f"{key}_url", "")).strip()
            parsed = urllib.parse.urlparse(url) if url else None
            if url and (parsed.scheme not in {"https", "http"} or not parsed.netloc):
                raise web.HTTPBadRequest(text=json.dumps({"error": f"Enter a valid http(s) link for {key.replace('_', ' ')}."}), content_type="application/json")
            offer[f"{key}_url"] = url
        await self.bot.db.set_settings_value(guild.id, "vc_reject_offer", offer, self.bot.settings.default_prefix)
        return web.json_response({"ok": True, "offer": offer})

    def _valid_shop_signature(self, guild_id: str, user_id: str, signature: str) -> bool:
        secret = self.bot.settings.oauth_state_secret or self.bot.settings.dashboard_token
        if not secret or not guild_id.isdigit() or not user_id.isdigit():
            return False
        expected = hmac.new(secret.encode(), f"{guild_id}:{user_id}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def shop(self, request: web.Request) -> web.Response:
        guild_id = request.query.get("guild_id", "")
        user_id = request.query.get("user_id", "")
        signature = request.query.get("signature", "")
        selected = request.query.get("product", "")
        promo = request.query.get("promo", "").strip().upper()[:32]
        if not self._valid_shop_signature(guild_id, user_id, signature):
            raise web.HTTPForbidden(text="This checkout link is invalid or incomplete.")
        guild = self.guild_or_404(guild_id)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        offer = settings.get("vc_reject_offer", {})
        products = [
            ("vc_perms", "VC Perms", offer.get("vc_perms_price", "15"), "Voice access permissions"),
            ("anti_reject", "Anti-Reject", offer.get("anti_reject_price", "20"), "Protected VC access"),
            ("godmode", "Godmode", offer.get("godmode_price", "30"), "Full VC protection"),
            ("all", "All Access", offer.get("all_price", "45"), "Complete access bundle"),
        ]
        cards = "".join(
            f'''<article class="product{' selected' if key == selected else ''}"><small>{html.escape(guild.name)}</small><h2>{html.escape(name)}</h2><div class="price">${html.escape(str(price))}</div><p>{html.escape(detail)}</p><a href="/checkout/start?{urllib.parse.urlencode({'guild_id':guild_id,'user_id':user_id,'signature':signature,'product':key,'promo':promo})}">Choose {html.escape(name)}</a></article>'''
            for key, name, price, detail in products
        )
        page = f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Voice Access</title><style>
        :root{{color-scheme:dark;--bg:#111210;--card:#1d1e1b;--line:#373832;--text:#f4f1e8;--muted:#aaa99f;--accent:#ff7043}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px Segoe UI,Arial,sans-serif}}main{{width:min(1050px,calc(100% - 28px));margin:auto;padding:60px 0}}header{{margin-bottom:28px}}h1{{font-size:clamp(38px,7vw,72px);letter-spacing:-.055em;margin:0}}header p,p{{color:var(--muted);line-height:1.55}}.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.product{{border:1px solid var(--line);background:var(--card);border-radius:16px;padding:22px}}.selected{{border-color:var(--accent)}}small{{color:var(--accent);text-transform:uppercase;letter-spacing:.12em}}h2{{font-size:24px;margin:14px 0 4px}}.price{{font-size:42px;font-weight:750}}a,button{{display:block;text-align:center;text-decoration:none;background:#2b2c27;border:1px solid #4b4c44;color:var(--text);padding:12px;border-radius:10px;font-weight:700;margin-top:18px}}input{{width:100%;background:#151613;border:1px solid var(--line);color:var(--text);padding:12px;border-radius:10px}}.promo{{margin:0 0 18px;padding:18px;border:1px solid var(--line);border-radius:14px}}.methods{{margin-top:22px;border-top:1px solid var(--line);padding-top:18px}}.methods span{{display:inline-block;border:1px solid var(--line);padding:7px 10px;border-radius:999px;margin:3px;color:var(--muted)}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}main{{padding-top:30px}}}}</style><main><header><h1>Choose your access</h1><p>Select a package, then complete payment securely through the hosted checkout.</p></header><form class="promo" method="get"><input type="hidden" name="guild_id" value="{html.escape(guild_id)}"><input type="hidden" name="user_id" value="{html.escape(user_id)}"><input type="hidden" name="signature" value="{html.escape(signature)}"><input type="hidden" name="product" value="{html.escape(selected)}"><label>Promo code</label><input name="promo" value="{html.escape(promo)}" placeholder="Enter code"><button type="submit">Apply code</button></form><section class="grid">{cards}</section><div class="methods"><span>Visa / credit card</span><span>Cash App Pay</span><span>Eligible crypto wallets</span><p>Available payment methods depend on your location and the seller's Stripe settings.</p></div></main>'''
        return web.Response(text=page, content_type="text/html")

    async def checkout_start(self, request: web.Request) -> web.Response:
        guild_id, user_id = request.query.get("guild_id", ""), request.query.get("user_id", "")
        signature, product = request.query.get("signature", ""), request.query.get("product", "")
        if not self._valid_shop_signature(guild_id, user_id, signature):
            raise web.HTTPForbidden(text="Invalid checkout link.")
        product_names = {"vc_perms": "VC Perms", "anti_reject": "Anti-Reject", "godmode": "Godmode", "all": "All Access"}
        if product not in product_names:
            raise web.HTTPBadRequest(text="Unknown product.")
        guild = self.guild_or_404(guild_id)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        offer = settings.get("vc_reject_offer", {})
        default_prices = {"vc_perms": "15", "anti_reject": "20", "godmode": "30", "all": "45"}
        price = float(offer.get(f"{product}_price", default_prices[product]))
        promo = request.query.get("promo", "").strip().upper()[:32]
        percent_off = 0
        if promo:
            with sqlite3.connect(self.oauth_db) as db:
                row = db.execute("SELECT percent_off,active,max_uses,uses FROM promo_codes WHERE guild_id=? AND code=?", (guild_id, promo)).fetchone()
            if row and row[1] and (row[2] == 0 or row[3] < row[2]):
                percent_off = int(row[0])
            else:
                raise web.HTTPBadRequest(text="That promo code is invalid, inactive, or fully used.")
        final_price = max(0.5, price * (100 - percent_off) / 100)
        secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
        public_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not secret_key or not public_url:
            raise web.HTTPServiceUnavailable(text="Checkout is not configured yet. Set STRIPE_SECRET_KEY and PUBLIC_BASE_URL.")
        form = {
            "mode": "payment", "success_url": f"{public_url}/checkout/success", "cancel_url": f"{public_url}/shop?{urllib.parse.urlencode(dict(request.query))}",
            "line_items[0][price_data][currency]": "usd", "line_items[0][price_data][product_data][name]": product_names[product],
            "line_items[0][price_data][unit_amount]": str(round(final_price * 100)), "line_items[0][quantity]": "1",
            "metadata[guild_id]": guild_id, "metadata[user_id]": user_id, "metadata[product]": product,
            "metadata[promo_code]": promo, "metadata[percent_off]": str(percent_off),
            "client_reference_id": f"discord_{user_id}",
        }
        async with ClientSession() as session:
            async with session.post("https://api.stripe.com/v1/checkout/sessions", data=form, auth=BasicAuth(secret_key, "")) as response:
                data = await response.json()
                if response.status >= 300 or not data.get("url"):
                    self.bot.log.error("Stripe Checkout error: %s", data.get("error", {}).get("message", data))
                    raise web.HTTPBadGateway(text="The payment provider could not start checkout.")
        raise web.HTTPFound(data["url"])

    async def checkout_success(self, _: web.Request) -> web.Response:
        return web.Response(text="<!doctype html><meta charset='utf-8'><body style='background:#111210;color:#f4f1e8;font:18px Segoe UI;padding:4rem'><h1>Payment received</h1><p>Your payment is being verified. Server staff can see confirmed payments in their dashboard.</p></body>", content_type="text/html")

    async def stripe_webhook(self, request: web.Request) -> web.Response:
        raw = await request.read()
        signature_header = request.headers.get("Stripe-Signature", "")
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        pieces = [part.split("=", 1) for part in signature_header.split(",") if "=" in part]
        timestamp = next((value for key, value in pieces if key == "t"), "")
        signatures = [value for key, value in pieces if key == "v1"]
        if not secret or not timestamp.isdigit() or abs(int(time.time()) - int(timestamp)) > 300:
            raise web.HTTPBadRequest(text="Invalid webhook signature.")
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, value) for value in signatures):
            raise web.HTTPBadRequest(text="Invalid webhook signature.")
        event = json.loads(raw)
        if event.get("type") == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            if session.get("payment_status") == "paid":
                metadata = session.get("metadata", {})
                customer = session.get("customer_details") or {}
                with sqlite3.connect(self.oauth_db) as db:
                    db.execute("""INSERT OR IGNORE INTO payment_logs(session_id,guild_id,user_id,product,amount,currency,customer_email,payment_methods,paid_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (session["id"], str(metadata.get("guild_id", "")), str(metadata.get("user_id", "")), str(metadata.get("product", "")), int(session.get("amount_total", 0)), str(session.get("currency", "usd")), customer.get("email"), ", ".join(session.get("payment_method_types", [])), int(time.time())))
                    promo = str(metadata.get("promo_code", "")).upper()
                    if promo:
                        inserted = db.execute("INSERT OR IGNORE INTO promo_uses(session_id,guild_id,code,user_id,used_at) VALUES(?,?,?,?,?)", (session["id"], str(metadata.get("guild_id", "")), promo, str(metadata.get("user_id", "")), int(time.time())))
                        if inserted.rowcount:
                            db.execute("UPDATE promo_codes SET uses=uses+1 WHERE guild_id=? AND code=?", (str(metadata.get("guild_id", "")), promo))
        return web.json_response({"received": True})

    async def payment_logs(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        with sqlite3.connect(self.oauth_db) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute("SELECT * FROM payment_logs WHERE guild_id=? ORDER BY paid_at DESC LIMIT 200", (str(guild.id),))]
        for row in rows:
            user = self.bot.get_user(int(row["user_id"])) if row["user_id"].isdigit() else None
            row["username"] = str(user) if user else "Unknown user"
            row["amount_display"] = f"{row['amount'] / 100:.2f} {row['currency'].upper()}"
        return web.json_response({"payments": rows, "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET") and os.getenv("PUBLIC_BASE_URL"))})

    async def promos(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        if request.method == "POST":
            body = await request.json()
            code = "".join(ch for ch in str(body.get("code", "")).upper() if ch.isalnum() or ch in "-_")[:32]
            percent = int(body.get("percent_off", 0) or 0)
            max_uses = int(body.get("max_uses", 0) or 0)
            if not code or not 1 <= percent <= 100 or max_uses < 0:
                raise web.HTTPBadRequest(text=json.dumps({"error": "Enter a code, 1-100 percent off, and a valid max-use count."}), content_type="application/json")
            with sqlite3.connect(self.oauth_db) as db:
                db.execute("INSERT INTO promo_codes(guild_id,code,percent_off,active,max_uses,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(guild_id,code) DO UPDATE SET percent_off=excluded.percent_off,active=excluded.active,max_uses=excluded.max_uses", (str(guild.id), code, percent, int(bool(body.get("active", True))), max_uses, int(time.time())))
        with sqlite3.connect(self.oauth_db) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute("SELECT p.*,GROUP_CONCAT(u.user_id) AS used_by FROM promo_codes p LEFT JOIN promo_uses u ON u.guild_id=p.guild_id AND u.code=p.code WHERE p.guild_id=? GROUP BY p.code ORDER BY p.created_at DESC", (str(guild.id),))]
        for row in rows:
            names = []
            for raw_id in str(row.get("used_by") or "").split(","):
                member = guild.get_member(int(raw_id)) if raw_id.isdigit() else None
                if member:
                    names.append(member.display_name)
            row["used_by"] = ", ".join(names)
        return web.json_response({"codes": rows})

    async def giveaway_config(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        if request.method == "POST":
            body = await request.json()
            outcomes = [{"name": str(x.get("name", ""))[:80], "weight": min(int(x.get("weight", 1) or 1), 10000)} for x in body.get("outcomes", [])[:50] if str(x.get("name", "")).strip() and int(x.get("weight", 0) or 0) > 0]
            await self.bot.db.set_settings_value(guild.id, "random_giveaway_outcomes", outcomes, self.bot.settings.default_prefix)
        else:
            outcomes = settings.get("random_giveaway_outcomes") or [{"name":"10% off","weight":35},{"name":"15% off","weight":25},{"name":"Nitro","weight":10},{"name":"$15 credit","weight":15}]
        return web.json_response({"outcomes": outcomes})

    async def live_channels(self, request: web.Request) -> web.Response:
        self.require_token(request)
        guild = self.guild_or_404(request.match_info["guild_id"])
        body = await request.json()
        if body.get("action") == "mvp":
            member = self.get_member_or_404(guild, body.get("member_id"))
            await self.bot.db.set_settings_value(guild.id, "mvp_winner_id", member.id, self.bot.settings.default_prefix)
        elif body.get("action") == "setup":
            category = discord.utils.get(guild.categories, name="Server Stats") or await guild.create_category("Server Stats", reason="Dashboard live-channel setup")
            try:
                await category.edit(position=0, reason="Keep live stats near the top")
            except discord.HTTPException:
                pass
            ids = {}
            settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
            old = settings.get("stats_channels", {})
            for key in ("members", "in vc", "top balance", "mvp winner", "giveaway winner"):
                channel = guild.get_channel(int(old.get(key, 0) or 0))
                if not isinstance(channel, discord.VoiceChannel):
                    channel = await guild.create_voice_channel(f"{key.title()}: --", category=category, reason="Dashboard live-channel setup")
                    await channel.set_permissions(guild.default_role, connect=False)
                ids[key] = channel.id
            await self.bot.db.set_settings_value(guild.id, "stats_channels", ids, self.bot.settings.default_prefix)
        growth = self.bot.get_cog("GrowthSafety")
        if growth:
            await growth.update_stats(guild)
        return web.json_response({"ok": True})

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
    app.router.add_get("/shop", dashboard.shop)
    app.router.add_get("/checkout/start", dashboard.checkout_start)
    app.router.add_get("/checkout/success", dashboard.checkout_success)
    app.router.add_post("/webhooks/stripe", dashboard.stripe_webhook)
    app.router.add_get("/api/guilds", dashboard.guilds)
    app.router.add_get("/api/owner-ids", dashboard.owner_ids)
    app.router.add_post("/api/owner-ids/add", dashboard.add_owner_id)
    app.router.add_post("/api/owner-ids/remove", dashboard.remove_owner_id)
    app.router.add_get("/api/guild/{guild_id}/vc-offer", dashboard.vc_offer_get)
    app.router.add_post("/api/guild/{guild_id}/vc-offer", dashboard.vc_offer_save)
    app.router.add_get("/api/guild/{guild_id}/payment-logs", dashboard.payment_logs)
    app.router.add_get("/api/guild/{guild_id}/promos", dashboard.promos)
    app.router.add_post("/api/guild/{guild_id}/promos", dashboard.promos)
    app.router.add_get("/api/guild/{guild_id}/giveaway-config", dashboard.giveaway_config)
    app.router.add_post("/api/guild/{guild_id}/giveaway-config", dashboard.giveaway_config)
    app.router.add_post("/api/guild/{guild_id}/live-channels", dashboard.live_channels)
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
