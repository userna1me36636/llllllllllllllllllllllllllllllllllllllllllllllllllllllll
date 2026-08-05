from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed, level_for_xp, style_embed


INVITE_RE = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.I)
LINK_RE = re.compile(r"https?://", re.I)


class StaffAppModal(discord.ui.Modal, title="Staff Application"):
    age = discord.ui.TextInput(label="Age", max_length=40)
    experience = discord.ui.TextInput(label="Experience", style=discord.TextStyle.paragraph, max_length=900)
    why = discord.ui.TextInput(label="Why should staff pick you?", style=discord.TextStyle.paragraph, max_length=900)

    def __init__(self, cog: "CommunitySuite") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.settings(interaction.guild_id)
        channel = interaction.guild.get_channel(int(settings.get("staff_app_channel", 0) or 0))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Application Channel Missing"), ephemeral=True)
            return
        e = await self.cog.themed(interaction.guild_id, "New Staff Application", f"Applicant: {interaction.user.mention}\nID: `{interaction.user.id}`")
        e.add_field(name="Age", value=str(self.age)[:1024], inline=False)
        e.add_field(name="Experience", value=str(self.experience)[:1024], inline=False)
        e.add_field(name="Why", value=str(self.why)[:1024], inline=False)
        await channel.send(embed=e, view=DecisionView(self.cog, "Application"))
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Application Sent"), ephemeral=True)


class StaffAppView(discord.ui.View):
    def __init__(self, cog: "CommunitySuite") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.primary, custom_id="staffapp:apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(StaffAppModal(self.cog))


class DecisionView(discord.ui.View):
    def __init__(self, cog: "CommunitySuite", label: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.label = label

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Missing Permission"), ephemeral=True)
        return False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.allowed(interaction):
            return
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, f"{self.label} Accepted"), ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.allowed(interaction):
            return
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, f"{self.label} Denied"), ephemeral=True)


class RulesView(discord.ui.View):
    def __init__(self, cog: "CommunitySuite") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Accept Rules", style=discord.ButtonStyle.success, custom_id="rules:accept")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = await self.cog.settings(interaction.guild_id)
        role = interaction.guild.get_role(int(settings.get("rules_role", 0) or 0))
        if not role or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Rules Role Missing"), ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="Accepted rules")
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Rules Accepted"), ephemeral=True)


class ReminderModal(discord.ui.Modal, title="Create Reminder"):
    minutes = discord.ui.TextInput(label="Minutes from now", placeholder="Example: 30", max_length=6)
    message = discord.ui.TextInput(label="Reminder", style=discord.TextStyle.paragraph, max_length=600)

    def __init__(self, cog: "CommunitySuite") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            minutes = max(1, min(10080, int(str(self.minutes))))
        except ValueError:
            await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Bad Minutes"), ephemeral=True)
            return
        reminders = (await self.cog.settings(interaction.guild_id)).get("button_reminders", [])
        reminders.append({"user_id": interaction.user.id, "channel_id": interaction.channel_id, "at": time.time() + minutes * 60, "message": str(self.message)[:600]})
        await self.cog.bot.db.set_settings_value(interaction.guild_id, "button_reminders", reminders[-200:], self.cog.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Reminder Set"), ephemeral=True)


class ReminderView(discord.ui.View):
    def __init__(self, cog: "CommunitySuite") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Set Reminder", style=discord.ButtonStyle.primary, custom_id="reminder:set")
    async def set_reminder(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ReminderModal(self.cog))


class CommunitySuite(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.voice_sessions: dict[tuple[int, int], float] = {}
        bot.add_view(RulesView(self))
        bot.add_view(StaffAppView(self))
        bot.add_view(ReminderView(self))
        self.birthday_loop.start()
        self.reminder_loop.start()
        self.voice_xp_loop.start()

    def cog_unload(self) -> None:
        self.birthday_loop.cancel()
        self.reminder_loop.cancel()
        self.voice_xp_loop.cancel()

    rules = app_commands.Group(name="rules", description="Rules accept panel")
    quarantine = app_commands.Group(name="quarantine", description="Quarantine tools")
    modmail = app_commands.Group(name="modmail", description="DM-to-staff mail")
    apply = app_commands.Group(name="apply", description="Staff applications")
    suggest = app_commands.Group(name="suggest", description="Suggestion tools")
    bug = app_commands.Group(name="bug", description="Bug reports")
    starboard = app_commands.Group(name="starboard", description="Starboard setup")
    cleanup = app_commands.Group(name="cleanup", description="Auto cleanup")
    backupbrowser = app_commands.Group(name="backupbrowser", description="Browse backup codes")
    custom = app_commands.Group(name="custom", description="Custom commands")
    birthday = app_commands.Group(name="birthday", description="Birthday system")
    boost = app_commands.Group(name="boost", description="Boost rewards")
    voicexp = app_commands.Group(name="voicexp", description="Voice XP and coins")
    reminders = app_commands.Group(name="reminderpanel", description="Reminder button panels")

    async def settings(self, guild_id: int) -> dict[str, Any]:
        return await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)

    async def themed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict[str, Any] = {}
        if guild_id is not None:
            settings = await self.settings(guild_id)
            theme = settings.get("theme", {})
            color = discord.Color(int(theme.get("color", color.value)))
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

    @rules.command(name="panel", description="Post rules with an accept button")
    @app_admin()
    async def rules_panel(self, interaction: discord.Interaction, role: discord.Role, text: str = "Read the rules, then press Accept.") -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "rules_role", role.id, self.bot.settings.default_prefix)
        await interaction.channel.send(embed=await self.themed(interaction.guild_id, "Server Rules", text[:1500]), view=RulesView(self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Rules Panel Posted"), ephemeral=True)

    @quarantine.command(name="setup", description="Set quarantine role")
    @app_admin()
    async def quarantine_setup(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "quarantine_role", role.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Quarantine Role Set"), ephemeral=True)

    @quarantine.command(name="user", description="Put a member in quarantine")
    @app_admin()
    async def quarantine_user(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Quarantine") -> None:
        role = interaction.guild.get_role(int((await self.settings(interaction.guild_id)).get("quarantine_role", 0) or 0))
        if not role:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Quarantine Role Missing"), ephemeral=True)
            return
        await member.add_roles(role, reason=reason)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "User Quarantined"), ephemeral=True)

    @modmail.command(name="setup", description="Set modmail staff channel")
    @app_admin()
    async def modmail_setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "modmail_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Modmail Channel Set"), ephemeral=True)

    @apply.command(name="panel", description="Post staff application panel")
    @app_admin()
    async def staff_apply_panel(self, interaction: discord.Interaction, review_channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "staff_app_channel", review_channel.id, self.bot.settings.default_prefix)
        await interaction.channel.send(embed=await self.themed(interaction.guild_id, "Staff Applications", "Press Apply to submit a staff application."), view=StaffAppView(self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Application Panel Posted"), ephemeral=True)

    @suggest.command(name="setup", description="Set suggestion channel")
    @app_admin()
    async def suggest_setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "suggest_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Suggestion Channel Set"), ephemeral=True)

    @suggest.command(name="send", description="Send a suggestion")
    async def suggest_send(self, interaction: discord.Interaction, text: str) -> None:
        channel = interaction.guild.get_channel(int((await self.settings(interaction.guild_id)).get("suggest_channel", 0) or 0))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Suggestion Channel Missing"), ephemeral=True)
            return
        msg = await channel.send(embed=await self.themed(interaction.guild_id, "Suggestion", f"{text[:1500]}\n\nBy {interaction.user.mention}"))
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Suggestion Sent"), ephemeral=True)

    @bug.command(name="setup", description="Set bug report channel")
    @app_admin()
    async def bug_setup(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "bug_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Bug Channel Set"), ephemeral=True)

    @bug.command(name="report", description="Report a bot/server bug")
    async def bug_report(self, interaction: discord.Interaction, text: str) -> None:
        channel = interaction.guild.get_channel(int((await self.settings(interaction.guild_id)).get("bug_channel", 0) or 0))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Bug Channel Missing"), ephemeral=True)
            return
        await channel.send(embed=await self.themed(interaction.guild_id, "Bug Report", f"{text[:1500]}\n\nBy {interaction.user.mention}"))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Bug Report Sent"), ephemeral=True)

    @starboard.command(name="setup", description="Set starboard channel and star count")
    @app_admin()
    async def starboard_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, stars: app_commands.Range[int, 1, 25] = 3) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "starboard", {"channel_id": channel.id, "stars": int(stars), "posted": {}}, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Starboard Set"), ephemeral=True)

    @cleanup.command(name="setup", description="Turn auto cleanup on/off")
    @app_admin()
    async def cleanup_setup(self, interaction: discord.Interaction, enabled: bool, invites: bool = True, links: bool = False, caps: bool = True, repeated: bool = True) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "auto_cleanup", {"enabled": enabled, "invites": invites, "links": links, "caps": caps, "repeated": repeated}, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Auto Cleanup Updated"), ephemeral=True)

    @backupbrowser.command(name="list", description="List backup codes")
    @app_admin()
    async def backup_list(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetchall("SELECT code,creator_id,used,created_at FROM backup_codes WHERE guild_id=? ORDER BY created_at DESC LIMIT 10", interaction.guild_id)
        e = await self.themed(interaction.guild_id, "Backup Browser")
        e.description = "\n".join(f"`{r['code']}` - used `{bool(r['used'])}` - by <@{r['creator_id']}> - {r['created_at']}" for r in rows) or "No backups found."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @backupbrowser.command(name="view", description="Preview a backup code")
    @app_admin()
    async def backup_view(self, interaction: discord.Interaction, code: str) -> None:
        row = await self.bot.db.fetchrow("SELECT snapshot,used,created_at FROM backup_codes WHERE code=?", code.upper())
        if row is None:
            await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Backup Not Found"), ephemeral=True)
            return
        data = json.loads(row["snapshot"])
        e = await self.themed(interaction.guild_id, "Backup Preview", f"Created: `{row['created_at']}`\nUsed: `{bool(row['used'])}`")
        e.add_field(name="Roles", value=f"`{len(data.get('roles', []))}`", inline=True)
        e.add_field(name="Categories", value=f"`{len(data.get('categories', []))}`", inline=True)
        e.add_field(name="Channels", value=f"`{len(data.get('channels', []))}`", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @custom.command(name="add", description="Add a simple custom prefix command")
    @app_admin()
    async def custom_add(self, interaction: discord.Interaction, name: str, response: str) -> None:
        settings = await self.settings(interaction.guild_id)
        cmds = settings.get("custom_commands", {})
        cmds[name.lower().strip()[:32]] = response[:1500]
        await self.bot.db.set_settings_value(interaction.guild_id, "custom_commands", cmds, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Custom Command Added"), ephemeral=True)

    @custom.command(name="remove", description="Remove a custom command")
    @app_admin()
    async def custom_remove(self, interaction: discord.Interaction, name: str) -> None:
        settings = await self.settings(interaction.guild_id)
        cmds = settings.get("custom_commands", {})
        cmds.pop(name.lower().strip(), None)
        await self.bot.db.set_settings_value(interaction.guild_id, "custom_commands", cmds, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Custom Command Removed"), ephemeral=True)

    @birthday.command(name="set", description="Set your birthday")
    async def birthday_set(self, interaction: discord.Interaction, month: app_commands.Range[int, 1, 12], day: app_commands.Range[int, 1, 31]) -> None:
        settings = await self.settings(interaction.guild_id)
        bdays = settings.get("birthdays", {})
        bdays[str(interaction.user.id)] = {"month": int(month), "day": int(day)}
        await self.bot.db.set_settings_value(interaction.guild_id, "birthdays", bdays, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Birthday Saved"), ephemeral=True)

    @birthday.command(name="channel", description="Set birthday announcement channel")
    @app_admin()
    async def birthday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "birthday_channel", channel.id, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Birthday Channel Set"), ephemeral=True)

    @boost.command(name="setup", description="Set booster role and coin reward")
    @app_admin()
    async def boost_setup(self, interaction: discord.Interaction, role: discord.Role | None = None, coins: app_commands.Range[int, 0, 1000000] = 0) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "boost_rewards", {"role_id": role.id if role else 0, "coins": int(coins), "given": {}}, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Boost Rewards Set"), ephemeral=True)

    @voicexp.command(name="setup", description="Configure VC XP and coins")
    @app_admin()
    async def voicexp_setup(self, interaction: discord.Interaction, enabled: bool, xp_per_5min: app_commands.Range[int, 0, 10000] = 25, coins_per_5min: app_commands.Range[int, 0, 10000] = 10) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "voice_xp", {"enabled": enabled, "xp": int(xp_per_5min), "coins": int(coins_per_5min)}, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Voice XP Updated"), ephemeral=True)

    @reminders.command(name="post", description="Post a reminder button panel")
    async def reminder_panel(self, interaction: discord.Interaction) -> None:
        await interaction.channel.send(embed=await self.themed(interaction.guild_id, "Reminders", "Press the button to create a reminder."), view=ReminderView(self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Reminder Panel Posted"), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            await self.handle_modmail_dm(message)
            return
        await self.handle_afk(message)
        await self.handle_custom_command(message)
        await self.handle_cleanup(message)

    async def handle_modmail_dm(self, message: discord.Message) -> None:
        for guild in self.bot.guilds:
            settings = await self.settings(guild.id)
            channel = guild.get_channel(int(settings.get("modmail_channel", 0) or 0))
            if isinstance(channel, discord.TextChannel):
                await channel.send(embed=await self.themed(guild.id, "Modmail", f"From {message.author} (`{message.author.id}`)\n\n{message.content[:1500]}"))
                try:
                    await message.channel.send("Your message was sent to staff.")
                except discord.HTTPException:
                    pass
                return

    async def handle_afk(self, message: discord.Message) -> None:
        settings = await self.settings(message.guild.id)
        afk = settings.get("afk_users", {})
        if str(message.author.id) in afk:
            afk.pop(str(message.author.id), None)
            await self.bot.db.set_settings_value(message.guild.id, "afk_users", afk, self.bot.settings.default_prefix)
            await message.reply(embed=await self.themed(message.guild.id, "Welcome Back"), mention_author=False)
        for member in message.mentions[:3]:
            data = afk.get(str(member.id))
            if data:
                await message.reply(embed=await self.themed(message.guild.id, "AFK", f"{member.mention}: {data.get('reason', 'AFK')}"), mention_author=False)

    async def handle_custom_command(self, message: discord.Message) -> None:
        settings = await self.settings(message.guild.id)
        prefix = settings.get("prefix", self.bot.settings.default_prefix)
        if not message.content.startswith(prefix):
            return
        name = message.content[len(prefix):].split(maxsplit=1)[0].lower()
        response = settings.get("custom_commands", {}).get(name)
        if response:
            await message.channel.send(embed=await self.themed(message.guild.id, name.title(), response))

    async def handle_cleanup(self, message: discord.Message) -> None:
        settings = await self.settings(message.guild.id)
        cfg = settings.get("auto_cleanup", {})
        if not cfg.get("enabled") or isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return
        content = message.content or ""
        bad = (cfg.get("invites") and INVITE_RE.search(content)) or (cfg.get("links") and LINK_RE.search(content)) or (cfg.get("caps") and len(content) > 12 and content.upper() == content)
        if bad:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    @commands.command(name="afk")
    async def afk_prefix(self, ctx: commands.Context, *, reason: str = "AFK") -> None:
        settings = await self.settings(ctx.guild.id)
        afk = settings.get("afk_users", {})
        afk[str(ctx.author.id)] = {"reason": reason[:500], "since": int(time.time())}
        await self.bot.db.set_settings_value(ctx.guild.id, "afk_users", afk, self.bot.settings.default_prefix)
        await ctx.reply(embed=await self.themed(ctx.guild.id, "AFK Set"), mention_author=False)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or str(payload.emoji) != "⭐":
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        settings = await self.settings(guild.id)
        cfg = settings.get("starboard", {})
        target = guild.get_channel(int(cfg.get("channel_id", 0) or 0))
        if not isinstance(target, discord.TextChannel):
            return
        posted = cfg.setdefault("posted", {})
        if str(payload.message_id) in posted:
            return
        source = guild.get_channel(payload.channel_id)
        if not isinstance(source, discord.TextChannel):
            return
        try:
            msg = await source.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        stars = 0
        for reaction in msg.reactions:
            if str(reaction.emoji) == "⭐":
                stars = reaction.count
                break
        if stars < int(cfg.get("stars", 3)):
            return
        e = await self.themed(guild.id, "Starboard", msg.content[:1500] or "No text content.")
        e.add_field(name="Author", value=msg.author.mention, inline=True)
        e.add_field(name="Jump", value=f"[Open message]({msg.jump_url})", inline=True)
        if msg.attachments:
            e.set_image(url=msg.attachments[0].url)
        sent = await target.send(embed=e)
        posted[str(msg.id)] = sent.id
        await self.bot.db.set_settings_value(guild.id, "starboard", cfg, self.bot.settings.default_prefix)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.premium_since == after.premium_since or after.premium_since is None:
            return
        settings = await self.settings(after.guild.id)
        cfg = settings.get("boost_rewards", {})
        given = cfg.setdefault("given", {})
        if str(after.id) in given:
            return
        role = after.guild.get_role(int(cfg.get("role_id", 0) or 0))
        if role:
            try:
                await after.add_roles(role, reason="Boost reward")
            except discord.HTTPException:
                pass
        coins = int(cfg.get("coins", 0) or 0)
        if coins:
            await self.bot.db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)", after.guild.id, after.id)
            await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", coins, after.guild.id, after.id)
        given[str(after.id)] = int(time.time())
        await self.bot.db.set_settings_value(after.guild.id, "boost_rewards", cfg, self.bot.settings.default_prefix)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if member.bot:
            return
        key = (member.guild.id, member.id)
        if before.channel is None and after.channel is not None:
            self.voice_sessions[key] = time.time()
        elif before.channel is not None and after.channel is None:
            self.voice_sessions.pop(key, None)

    @tasks.loop(minutes=5)
    async def voice_xp_loop(self) -> None:
        now = time.time()
        for guild in self.bot.guilds:
            settings = await self.settings(guild.id)
            cfg = settings.get("voice_xp", {})
            if not cfg.get("enabled"):
                continue
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot:
                        continue
                    await self.bot.db.execute("INSERT OR IGNORE INTO xp(guild_id,user_id) VALUES(?,?)", guild.id, member.id)
                    await self.bot.db.execute("UPDATE xp SET amount=amount+?, last_message_at=? WHERE guild_id=? AND user_id=?", int(cfg.get("xp", 25)), now, guild.id, member.id)
                    await self.bot.db.execute("INSERT OR IGNORE INTO economy(guild_id,user_id) VALUES(?,?)", guild.id, member.id)
                    await self.bot.db.execute("UPDATE economy SET wallet=wallet+? WHERE guild_id=? AND user_id=?", int(cfg.get("coins", 10)), guild.id, member.id)

    @voice_xp_loop.before_loop
    async def before_voice_xp_loop(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def birthday_loop(self) -> None:
        today = dt.datetime.now().date()
        for guild in self.bot.guilds:
            settings = await self.settings(guild.id)
            channel = guild.get_channel(int(settings.get("birthday_channel", 0) or 0))
            if not isinstance(channel, discord.TextChannel):
                continue
            sent_key = f"{today.isoformat()}"
            sent = settings.get("birthday_sent", {})
            for user_id, data in settings.get("birthdays", {}).items():
                if int(data.get("month", 0)) == today.month and int(data.get("day", 0)) == today.day and sent.get(user_id) != sent_key:
                    await channel.send(embed=await self.themed(guild.id, "Happy Birthday", f"Happy birthday <@{user_id}>!"))
                    sent[user_id] = sent_key
            await self.bot.db.set_settings_value(guild.id, "birthday_sent", sent, self.bot.settings.default_prefix)

    @birthday_loop.before_loop
    async def before_birthday_loop(self) -> None:
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=45)
    async def reminder_loop(self) -> None:
        now = time.time()
        for guild in self.bot.guilds:
            settings = await self.settings(guild.id)
            reminders = settings.get("button_reminders", [])
            remaining = []
            changed = False
            for reminder in reminders:
                if float(reminder.get("at", 0)) <= now:
                    channel = guild.get_channel(int(reminder.get("channel_id", 0) or 0))
                    if isinstance(channel, discord.TextChannel):
                        await channel.send(f"<@{reminder.get('user_id')}>", embed=await self.themed(guild.id, "Reminder", str(reminder.get("message", ""))[:600]))
                    changed = True
                else:
                    remaining.append(reminder)
            if changed:
                await self.bot.db.set_settings_value(guild.id, "button_reminders", remaining, self.bot.settings.default_prefix)

    @reminder_loop.before_loop
    async def before_reminder_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunitySuite(bot))
