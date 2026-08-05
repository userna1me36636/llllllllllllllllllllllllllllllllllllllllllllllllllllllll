from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin, configured_owner, has_guild_permissions
from bot.core.utils import embed, level_for_xp, style_embed


DANGEROUS_PERMS = (
    "administrator",
    "ban_members",
    "kick_members",
    "manage_roles",
    "manage_channels",
    "manage_guild",
    "manage_webhooks",
    "moderate_members",
)


class LockdownConfirmView(discord.ui.View):
    def __init__(self, cog: "GrowthSafety", reason: str) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.reason = reason

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions if isinstance(interaction.user, discord.Member) else None
        if perms and perms.manage_guild:
            return True
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Missing Permission"), ephemeral=True)
        return False

    @discord.ui.button(label="Confirm Lockdown", style=discord.ButtonStyle.danger)
    async def confirm_lockdown(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        locked = await self.cog.apply_lockdown(interaction, self.reason)
        await interaction.followup.send(embed=await self.cog.themed(interaction.guild_id, "Security Lockdown", f"Locked `{locked}` text channels."), ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=await self.cog.themed(interaction.guild_id, "Lockdown Cancelled"), view=None)


class AppealModal(discord.ui.Modal, title="Submit Appeal"):
    reason = discord.ui.TextInput(label="Why should staff review this?", style=discord.TextStyle.paragraph, max_length=900)
    proof = discord.ui.TextInput(label="Proof or extra info", style=discord.TextStyle.paragraph, required=False, max_length=900)

    def __init__(self, cog: "GrowthSafety") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        channel_id = settings.get("appeal_channel")
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Appeal Channel Missing"), ephemeral=True)
            return
        e = await self.cog.themed(interaction.guild_id, "New Appeal", f"User: {interaction.user.mention}\nID: `{interaction.user.id}`")
        e.add_field(name="Reason", value=str(self.reason)[:1024], inline=False)
        if str(self.proof).strip():
            e.add_field(name="Proof", value=str(self.proof)[:1024], inline=False)
        await channel.send(embed=e)
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Appeal Sent"), ephemeral=True)


class AppealView(discord.ui.View):
    def __init__(self, cog: "GrowthSafety") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Submit Appeal", style=discord.ButtonStyle.primary, custom_id="appeal:submit")
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(AppealModal(self.cog))


class VerifyView(discord.ui.View):
    def __init__(self, cog: "GrowthSafety") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, custom_id="verify:button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        settings = await self.cog.bot.db.get_settings(interaction.guild_id, self.cog.bot.settings.default_prefix)
        role_id = settings.get("verify_role")
        role = interaction.guild.get_role(int(role_id)) if role_id else None
        if not isinstance(role, discord.Role) or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Verify Role Missing"), ephemeral=True)
            return
        min_age = int(settings.get("verify_min_account_days", 0) or 0)
        if min_age:
            age_days = (discord.utils.utcnow() - interaction.user.created_at).days
            if age_days < min_age:
                await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Account Too New", f"Account age: `{age_days}` days\nRequired: `{min_age}` days"), ephemeral=True)
                return
        await interaction.user.add_roles(role, reason="Verification button")
        await interaction.response.send_message(embed=await self.cog.themed(interaction.guild_id, "Verified"), ephemeral=True)


class GrowthSafety(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.join_times: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=40))
        self.invite_cache: dict[int, dict[str, int]] = {}
        bot.add_view(AppealView(self))
        bot.add_view(VerifyView(self))
        self.stats_updater.start()

    def cog_unload(self) -> None:
        self.stats_updater.cancel()

    security = app_commands.Group(name="security", description="Raid mode, lockdown, and role audit")
    appeal = app_commands.Group(name="appeal", description="Appeal panel tools")
    notes = app_commands.Group(name="notes", description="Private staff notes")
    verify = app_commands.Group(name="verify", description="Verification panel")
    invite = app_commands.Group(name="invite", description="Invite tracking")
    stats = app_commands.Group(name="stats", description="Server stat channels")
    builder = app_commands.Group(name="builder", description="Builders for reaction roles and shops")
    store = app_commands.Group(name="store", description="Custom economy shop")
    levelrewards = app_commands.Group(name="levelrewards", description="Automatic level role rewards")
    staff = app_commands.Group(name="staff", description="Staff activity tools")

    async def themed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict[str, Any] = {}
        if guild_id is not None:
            settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
            theme = settings.get("theme", {})
            color = discord.Color(int(theme.get("color", color.value)))
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

    async def log_staff_action(self, guild_id: int, user_id: int, action: str) -> None:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        activity = settings.get("staff_activity", {})
        data = activity.setdefault(str(user_id), {})
        data[action] = int(data.get(action, 0)) + 1
        data["total"] = int(data.get("total", 0)) + 1
        await self.bot.db.set_settings_value(guild_id, "staff_activity", activity, self.bot.settings.default_prefix)

    async def get_invites(self, guild: discord.Guild) -> dict[str, int]:
        try:
            invites = await guild.invites()
            return {invite.code: invite.uses or 0 for invite in invites}
        except discord.HTTPException:
            return {}

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            self.invite_cache[guild.id] = await self.get_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild:
            self.invite_cache[invite.guild.id] = await self.get_invites(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild:
            self.invite_cache[invite.guild.id] = await self.get_invites(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.track_invite(member)
        await self.handle_raid_mode(member)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        actor = None
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == user.id:
                    actor = entry.user
                    break
        except discord.HTTPException:
            return
        if actor and not actor.bot:
            await self.log_staff_action(guild.id, actor.id, "bans")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            try:
                async for entry in after.guild.audit_logs(limit=3, action=discord.AuditLogAction.member_update):
                    if entry.target and entry.target.id == after.id and entry.user and not entry.user.bot:
                        await self.log_staff_action(after.guild.id, entry.user.id, "timeouts")
                        break
            except discord.HTTPException:
                pass
        await self.apply_level_rewards(after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        await self.maybe_auto_publish(message)
        if isinstance(message.author, discord.Member):
            await self.apply_level_rewards(message.author)

    async def track_invite(self, member: discord.Member) -> None:
        before = self.invite_cache.get(member.guild.id, {})
        after = await self.get_invites(member.guild)
        used_code = None
        for code, uses in after.items():
            if uses > before.get(code, 0):
                used_code = code
                break
        self.invite_cache[member.guild.id] = after
        if used_code is None:
            return
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        data = settings.get("invite_tracker", {})
        code_data = data.setdefault(used_code, {"joins": 0})
        code_data["joins"] = int(code_data.get("joins", 0)) + 1
        data[f"user:{member.id}"] = used_code
        await self.bot.db.set_settings_value(member.guild.id, "invite_tracker", data, self.bot.settings.default_prefix)

    async def handle_raid_mode(self, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        raid = settings.get("raid_mode", {})
        if not raid.get("enabled"):
            return
        now = time.time()
        joins = self.join_times[member.guild.id]
        joins.append(now)
        seconds = int(raid.get("seconds", 30))
        threshold = int(raid.get("threshold", 8))
        recent = [stamp for stamp in joins if now - stamp <= seconds]
        if len(recent) < threshold:
            return
        channel_ids = set()
        for key in ("welcome", "setup"):
            value = settings.get(key, {})
            if isinstance(value, dict):
                for channel_id in value.values():
                    if isinstance(channel_id, int):
                        channel_ids.add(channel_id)
        if settings.get("logs_channel"):
            channel_ids.add(int(settings["logs_channel"]))
        locked = 0
        for channel_id in channel_ids:
            channel = member.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.set_permissions(member.guild.default_role, send_messages=False, reason="Raid mode auto-lock")
                    locked += 1
                except discord.HTTPException:
                    pass
        log_channel = member.guild.get_channel(int(settings.get("logs_channel", 0) or 0))
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(embed=await self.themed(member.guild.id, "Raid Mode Triggered", f"`{len(recent)}` joins in `{seconds}` seconds.\nLocked `{locked}` configured channel(s)."))

    async def maybe_auto_publish(self, message: discord.Message) -> None:
        if not hasattr(message.channel, "is_news") or not message.channel.is_news():
            return
        settings = await self.bot.db.get_settings(message.guild.id, self.bot.settings.default_prefix)
        if settings.get("auto_publish_enabled", False) is not True:
            return
        try:
            await message.publish()
        except discord.HTTPException:
            pass

    async def apply_level_rewards(self, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
        rewards = settings.get("level_rewards", {})
        if not rewards:
            return
        row = await self.bot.db.fetchrow("SELECT amount FROM xp WHERE guild_id=? AND user_id=?", member.guild.id, member.id)
        lvl = level_for_xp(row["amount"] if row else 0)
        for level_text, role_id in rewards.items():
            if lvl >= int(level_text):
                role = member.guild.get_role(int(role_id))
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Level reward {level_text}")
                    except discord.HTTPException:
                        pass

    @security.command(name="raidmode", description="Turn raid mode on/off")
    @app_admin()
    async def raidmode(self, interaction: discord.Interaction, enabled: bool, threshold: app_commands.Range[int, 3, 50] = 8, seconds: app_commands.Range[int, 10, 600] = 30) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "raid_mode", {"enabled": enabled, "threshold": int(threshold), "seconds": int(seconds)}, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Raid Mode Updated", f"Enabled: `{enabled}`\nTrigger: `{threshold}` joins in `{seconds}` seconds"), ephemeral=True)

    @security.command(name="lockdown", description="Lock every text channel the bot can manage")
    @app_admin()
    async def lockdown(self, interaction: discord.Interaction, reason: str = "Security lockdown") -> None:
        await interaction.response.send_message(
            embed=await self.themed(interaction.guild_id, "Confirm Lockdown", "This will lock every text channel I can manage."),
            view=LockdownConfirmView(self, reason),
            ephemeral=True,
        )

    async def apply_lockdown(self, interaction: discord.Interaction, reason: str) -> int:
        locked = 0
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(interaction.guild.default_role, send_messages=False, reason=reason)
                locked += 1
            except discord.HTTPException:
                pass
        await self.bot.db.set_settings_value(interaction.guild_id, "security_lockdown", True, self.bot.settings.default_prefix)
        return locked

    @security.command(name="unlockdown", description="Undo bot lockdown on text channels")
    @app_admin()
    async def unlockdown(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        unlocked = 0
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(interaction.guild.default_role, send_messages=None, reason="Lockdown lifted")
                unlocked += 1
            except discord.HTTPException:
                pass
        await self.bot.db.set_settings_value(interaction.guild_id, "security_lockdown", False, self.bot.settings.default_prefix)
        await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Lockdown Lifted", f"Unlocked `{unlocked}` text channels."), ephemeral=True)

    @security.command(name="roleaudit", description="Show dangerous/unmanageable roles")
    @app_admin()
    async def roleaudit(self, interaction: discord.Interaction) -> None:
        me = interaction.guild.me
        lines = []
        for role in sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default():
                continue
            dangerous = [name for name in DANGEROUS_PERMS if getattr(role.permissions, name)]
            above_bot = role >= me.top_role
            if dangerous or above_bot:
                tags = []
                if above_bot:
                    tags.append("above bot")
                if dangerous:
                    tags.append(", ".join(dangerous[:3]))
                lines.append(f"{role.mention} - `{'; '.join(tags)}`")
        e = await self.themed(interaction.guild_id, "Role Audit")
        e.add_field(name="Roles To Review", value="\n".join(lines[:20])[:1024] or "No obvious role issues found.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @appeal.command(name="panel", description="Post an appeal button panel")
    @app_admin()
    async def appeal_panel(self, interaction: discord.Interaction, review_channel: discord.TextChannel, post_channel: discord.TextChannel | None = None) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "appeal_channel", review_channel.id, self.bot.settings.default_prefix)
        target = post_channel or interaction.channel
        await target.send(embed=await self.themed(interaction.guild_id, "Appeals", "Press the button below to submit an appeal to staff."), view=AppealView(self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Appeal Panel Posted"), ephemeral=True)

    @notes.command(name="add", description="Add a private staff note")
    @app_admin()
    async def note_add(self, interaction: discord.Interaction, member: discord.Member, note: str) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        notes = settings.get("staff_notes", {})
        rows = notes.setdefault(str(member.id), [])
        rows.append({"mod": interaction.user.id, "note": note[:700], "time": int(time.time())})
        await self.bot.db.set_settings_value(interaction.guild_id, "staff_notes", notes, self.bot.settings.default_prefix)
        await self.log_staff_action(interaction.guild_id, interaction.user.id, "notes")
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Note Added"), ephemeral=True)

    @notes.command(name="list", description="List private staff notes")
    @app_admin()
    async def note_list(self, interaction: discord.Interaction, member: discord.Member) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        rows = settings.get("staff_notes", {}).get(str(member.id), [])
        e = await self.themed(interaction.guild_id, "Staff Notes", member.mention)
        for idx, row in enumerate(rows[-10:], start=1):
            e.add_field(name=f"#{idx} by <@{row.get('mod')}>", value=str(row.get("note", ""))[:700], inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @verify.command(name="panel", description="Post verification panel")
    @app_admin()
    async def verify_panel(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel | None = None, min_account_days: app_commands.Range[int, 0, 365] = 0) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "verify_role", role.id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(interaction.guild_id, "verify_min_account_days", int(min_account_days), self.bot.settings.default_prefix)
        target = channel or interaction.channel
        await target.send(embed=await self.themed(interaction.guild_id, "Verify", f"Press the button to receive {role.mention}."), view=VerifyView(self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Verification Panel Posted"), ephemeral=True)

    @invite.command(name="leaderboard", description="Show invite code leaderboard")
    async def invite_leaderboard(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        data = settings.get("invite_tracker", {})
        codes = [(code, info.get("joins", 0)) for code, info in data.items() if isinstance(info, dict)]
        codes.sort(key=lambda item: item[1], reverse=True)
        e = await self.themed(interaction.guild_id, "Invite Leaderboard")
        e.description = "\n".join(f"`{code}` - `{joins}` joins" for code, joins in codes[:10]) or "No invite data tracked yet."
        await interaction.response.send_message(embed=e)

    @stats.command(name="setup", description="Create/update server stat channels")
    @app_admin()
    async def stats_setup(self, interaction: discord.Interaction, category: discord.CategoryChannel | None = None) -> None:
        await interaction.response.defer(ephemeral=True)
        category = category or await interaction.guild.create_category("Server Stats", reason="Stats setup")
        existing = {channel.name.split(":")[0].lower(): channel for channel in category.voice_channels}
        ids = {}
        for key in ("Members", "Boosts", "Roles"):
            channel = existing.get(key.lower())
            if channel is None:
                channel = await interaction.guild.create_voice_channel(f"{key}: 0", category=category, reason="Stats setup")
                await channel.set_permissions(interaction.guild.default_role, connect=False)
            ids[key.lower()] = channel.id
        await self.bot.db.set_settings_value(interaction.guild_id, "stats_channels", ids, self.bot.settings.default_prefix)
        await self.update_stats(interaction.guild)
        await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Stats Channels Ready"), ephemeral=True)

    async def update_stats(self, guild: discord.Guild) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        ids = settings.get("stats_channels", {})
        values = {"members": len(guild.members), "boosts": guild.premium_subscription_count or 0, "roles": len(guild.roles)}
        for key, value in values.items():
            channel = guild.get_channel(int(ids.get(key, 0) or 0))
            if isinstance(channel, discord.VoiceChannel) and channel.name != f"{key.title()}: {value}":
                try:
                    await channel.edit(name=f"{key.title()}: {value}")
                except discord.HTTPException:
                    pass

    @tasks.loop(minutes=10)
    async def stats_updater(self) -> None:
        for guild in self.bot.guilds:
            await self.update_stats(guild)

    @stats_updater.before_loop
    async def before_stats_updater(self) -> None:
        await self.bot.wait_until_ready()

    @builder.command(name="reactionrole", description="Post a button role panel")
    @app_admin()
    async def reactionrole_builder(self, interaction: discord.Interaction, role: discord.Role, title: str = "Get Roles", description: str = "Press the button to toggle the role.") -> None:
        class RoleButton(discord.ui.View):
            def __init__(self, target_role: discord.Role, cog: "GrowthSafety") -> None:
                super().__init__(timeout=None)
                self.target_role = target_role
                self.cog = cog

            @discord.ui.button(label="Toggle Role", style=discord.ButtonStyle.secondary)
            async def toggle_role(self, i: discord.Interaction, b: discord.ui.Button) -> None:
                if not isinstance(i.user, discord.Member):
                    return
                if self.target_role in i.user.roles:
                    await i.user.remove_roles(self.target_role, reason="Button role remove")
                    await i.response.send_message(embed=await self.cog.themed(i.guild_id, "Role Removed"), ephemeral=True)
                else:
                    await i.user.add_roles(self.target_role, reason="Button role add")
                    await i.response.send_message(embed=await self.cog.themed(i.guild_id, "Role Added"), ephemeral=True)

        await interaction.channel.send(embed=await self.themed(interaction.guild_id, title, description), view=RoleButton(role, self))
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Reaction Role Panel Posted"), ephemeral=True)

    @store.command(name="add", description="Add a custom shop role item")
    @app_admin()
    async def store_add(self, interaction: discord.Interaction, name: str, price: app_commands.Range[int, 1, 100_000_000], role: discord.Role) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        shop = settings.get("custom_shop", {})
        shop[name.lower()] = {"price": int(price), "role_id": role.id}
        await self.bot.db.set_settings_value(interaction.guild_id, "custom_shop", shop, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Shop Item Added"), ephemeral=True)

    @store.command(name="list", description="List custom shop items")
    async def store_list(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        shop = settings.get("custom_shop", {})
        e = await self.themed(interaction.guild_id, "Custom Shop")
        e.description = "\n".join(f"`{name}` - `{item['price']}` coins - <@&{item['role_id']}>" for name, item in shop.items()) or "No custom items yet."
        await interaction.response.send_message(embed=e)

    @store.command(name="buy", description="Buy a custom shop role item")
    async def store_buy(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        item = settings.get("custom_shop", {}).get(name.lower())
        if not item:
            await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Item Not Found"), ephemeral=True)
            return
        row = await self.bot.db.fetchrow("SELECT wallet FROM economy WHERE guild_id=? AND user_id=?", interaction.guild_id, interaction.user.id)
        wallet = row["wallet"] if row else 0
        price = int(item["price"])
        if wallet < price:
            await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Not Enough Coins"), ephemeral=True)
            return
        role = interaction.guild.get_role(int(item["role_id"]))
        if not role or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Role Missing"), ephemeral=True)
            return
        await self.bot.db.execute("UPDATE economy SET wallet=wallet-? WHERE guild_id=? AND user_id=?", price, interaction.guild_id, interaction.user.id)
        await interaction.user.add_roles(role, reason=f"Bought shop item {name}")
        await interaction.followup.send(embed=await self.themed(interaction.guild_id, "Item Bought"), ephemeral=True)

    @levelrewards.command(name="add", description="Give a role automatically at a level")
    @app_admin()
    async def reward_add(self, interaction: discord.Interaction, level: app_commands.Range[int, 1, 1000], role: discord.Role) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        rewards = settings.get("level_rewards", {})
        rewards[str(int(level))] = role.id
        await self.bot.db.set_settings_value(interaction.guild_id, "level_rewards", rewards, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Level Reward Added"), ephemeral=True)

    @levelrewards.command(name="list", description="List level rewards")
    async def reward_list(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        rewards = settings.get("level_rewards", {})
        e = await self.themed(interaction.guild_id, "Level Rewards")
        e.description = "\n".join(f"Level `{level}` - <@&{role_id}>" for level, role_id in sorted(rewards.items(), key=lambda x: int(x[0]))) or "No rewards set."
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="case", description="Show moderation case history for a member")
    @app_admin()
    async def case_history(self, interaction: discord.Interaction, member: discord.Member) -> None:
        rows = await self.bot.db.fetchall("SELECT id,action,moderator_id,reason,created_at FROM cases WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10", interaction.guild_id, member.id)
        e = await self.themed(interaction.guild_id, "Case History", member.mention)
        for row in rows:
            e.add_field(name=f"#{row['id']} {row['action']}", value=f"Mod: <@{row['moderator_id']}>\nReason: {row['reason'] or 'None'}\n{row['created_at']}", inline=False)
        if not rows:
            e.description = f"{member.mention}\nNo cases found."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @staff.command(name="activity", description="Show staff activity counts")
    @app_admin()
    async def staff_activity(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        activity = settings.get("staff_activity", {})
        rows = sorted(activity.items(), key=lambda x: int(x[1].get("total", 0)), reverse=True)
        e = await self.themed(interaction.guild_id, "Staff Activity")
        e.description = "\n".join(f"<@{user_id}> - `{data.get('total', 0)}` actions" for user_id, data in rows[:15]) or "No activity tracked yet."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="autopublish", description="Turn auto-publish for announcement channels on/off")
    @app_admin()
    async def autopublish(self, interaction: discord.Interaction, enabled: bool) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "auto_publish_enabled", enabled, self.bot.settings.default_prefix)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Auto Publish Updated", f"Enabled: `{enabled}`"), ephemeral=True)

    @commands.command(name="roleaudit")
    @has_guild_permissions(manage_guild=True)
    async def prefix_roleaudit(self, ctx: commands.Context) -> None:
        me = ctx.guild.me
        lines = []
        for role in sorted(ctx.guild.roles, key=lambda r: r.position, reverse=True):
            if role.is_default():
                continue
            dangerous = [name for name in DANGEROUS_PERMS if getattr(role.permissions, name)]
            if dangerous or role >= me.top_role:
                lines.append(f"{role.mention} - `{', '.join(dangerous[:3]) or 'above bot'}`")
        e = await self.themed(ctx.guild.id, "Role Audit")
        e.description = "\n".join(lines[:20])[:4000] or "No obvious role issues found."
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GrowthSafety(bot))
