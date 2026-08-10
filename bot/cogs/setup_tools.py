from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed, style_embed, theme_color_from_data


DANGEROUS_PERMS = (
    "administrator",
    "ban_members",
    "kick_members",
    "manage_roles",
    "manage_channels",
    "manage_guild",
    "manage_webhooks",
    "moderate_members",
    "view_audit_log",
)


SERVER_TEMPLATES: dict[str, dict[str, object]] = {
    "community": {
        "label": "Community",
        "description": "A clean social server for conversation, events, media and member support.",
        "roles": ["Verified", "Moderator", "Event Host", "Giveaway Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "announcements", "verify"],
            "COMMUNITY": ["general", "media", "memes", "suggestions", "bot-commands"],
            "EVENTS": ["events", "giveaways", "polls"],
            "SUPPORT": ["faq", "open-a-ticket"],
            "VOICE": ["General VC", "Gaming VC", "Music VC"],
        },
    },
    "gaming": {
        "label": "Gaming",
        "description": "A gaming hub for squads, clips, looking-for-group posts and tournaments.",
        "roles": ["Verified", "Moderator", "Event Host", "LFG Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "announcements", "verify"],
            "GAMING": ["general", "looking-for-group", "clips", "game-news", "tournaments"],
            "COMMUNITY": ["media", "memes", "suggestions", "bot-commands"],
            "SUPPORT": ["faq", "open-a-ticket"],
            "VOICE": ["Lobby", "Squad One", "Squad Two", "AFK"],
        },
    },
    "music": {
        "label": "Music and Artist",
        "description": "A music community for releases, feedback, collaborations and listening sessions.",
        "roles": ["Verified", "Moderator", "Artist", "Producer", "Release Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "announcements", "verify"],
            "MUSIC": ["releases", "self-promo", "feedback", "collaborations", "beats-and-samples"],
            "COMMUNITY": ["general", "media", "events", "bot-commands"],
            "SUPPORT": ["faq", "open-a-ticket"],
            "VOICE": ["Studio", "Listening Party", "Open Mic"],
        },
    },
    "creator": {
        "label": "Creator",
        "description": "A creator community for content drops, feedback, collaborations and supporters.",
        "roles": ["Verified", "Moderator", "Creator", "Collaborator", "Upload Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "announcements", "verify"],
            "CONTENT": ["new-content", "clips", "ideas", "feedback", "collaborations"],
            "COMMUNITY": ["general", "media", "suggestions", "bot-commands"],
            "SUPPORT": ["faq", "open-a-ticket"],
            "VOICE": ["Creator Lounge", "Recording Room", "Community VC"],
        },
    },
    "business": {
        "label": "Business",
        "description": "A professional client and team space with updates, resources and private support.",
        "roles": ["Verified", "Administrator", "Team", "Client", "Updates Ping"],
        "categories": {
            "INFORMATION": ["welcome", "rules", "announcements", "services"],
            "CLIENTS": ["client-chat", "resources", "testimonials", "updates"],
            "SUPPORT": ["faq", "open-a-ticket"],
            "TEAM": ["team-chat", "team-tasks", "team-logs"],
            "VOICE": ["Client Meeting", "Team Meeting", "Waiting Room"],
        },
    },
    "marketplace": {
        "label": "Marketplace",
        "description": "A moderated marketplace for listings, reviews, support and transaction guidance.",
        "roles": ["Verified", "Moderator", "Seller", "Buyer", "Listing Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "marketplace-rules", "verify"],
            "MARKET": ["listings", "buying", "selling", "price-checks", "reviews"],
            "COMMUNITY": ["general", "vouches", "suggestions"],
            "SUPPORT": ["faq", "report-a-user", "open-a-ticket"],
            "VOICE": ["Market Lounge", "Support Waiting"],
        },
    },
    "support": {
        "label": "Product Support",
        "description": "A focused support server with documentation, incidents, tickets and customer updates.",
        "roles": ["Verified", "Support Lead", "Support Team", "Customer", "Status Ping"],
        "categories": {
            "INFORMATION": ["welcome", "rules", "announcements", "status"],
            "HELP CENTER": ["getting-started", "faq", "known-issues", "open-a-ticket"],
            "COMMUNITY": ["general", "suggestions", "showcase"],
            "STAFF": ["staff-chat", "support-queue", "bot-logs"],
            "VOICE": ["Support Waiting", "Support Room One", "Support Room Two"],
        },
    },
    "roleplay": {
        "label": "Roleplay",
        "description": "A roleplay server with lore, character creation, scenes and out-of-character spaces.",
        "roles": ["Verified", "Moderator", "Game Master", "Player", "Event Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "lore", "verify"],
            "CHARACTERS": ["character-rules", "character-submissions", "approved-characters"],
            "ROLEPLAY": ["scene-one", "scene-two", "events"],
            "OUT OF CHARACTER": ["general", "media", "suggestions"],
            "VOICE": ["OOC Lounge", "Roleplay Room One", "Roleplay Room Two"],
        },
    },
    "esports": {
        "label": "Esports Team",
        "description": "A competitive team server for tryouts, schedules, strategy and match operations.",
        "roles": ["Verified", "Coach", "Team Captain", "Player", "Tryout"],
        "categories": {
            "INFORMATION": ["welcome", "rules", "announcements", "schedule"],
            "TEAM": ["team-chat", "strategy", "vod-review", "scrims", "results"],
            "RECRUITMENT": ["tryout-info", "applications", "open-a-ticket"],
            "COMMUNITY": ["general", "clips", "suggestions"],
            "VOICE": ["Team One", "Team Two", "Coach Room", "Tryouts"],
        },
    },
    "study": {
        "label": "Study and School",
        "description": "A study community for accountability, resources, subjects and quiet work rooms.",
        "roles": ["Verified", "Moderator", "Tutor", "Study Ping"],
        "categories": {
            "START HERE": ["welcome", "rules", "announcements", "verify"],
            "STUDY": ["study-chat", "questions", "resources", "goals", "accountability"],
            "SUBJECTS": ["math", "science", "writing", "technology"],
            "COMMUNITY": ["general", "break-room", "suggestions"],
            "VOICE": ["Silent Study", "Group Study", "Tutoring"],
        },
    },
}


class SetupTools(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    setup = app_commands.Group(name="setup", description="Fast bot setup tools")
    dashboard = app_commands.Group(name="dashboard", description="Clean setup/status dashboards")
    scan = app_commands.Group(name="scan", description="Server scan tools")

    async def themed(self, guild_id: int | None, title: str, description: str | None = None) -> discord.Embed:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict = {}
        if guild_id is not None:
            settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
            theme = settings.get("theme", {})
            color = theme_color_from_data(theme, color)
        e = embed(title, description, color)
        style_embed(e, banner_url=theme.get("banner_url"), flashy=False)
        return e

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        self.bot.log.exception("Setup command failed", exc_info=error)
        message = f"Setup stopped: `{type(error).__name__}`. Check the bot's role permissions and Railway logs."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

    @setup.command(name="wizard", description="Set the main channels/categories the bot should use")
    @app_admin()
    async def setup_wizard(
        self,
        interaction: discord.Interaction,
        logs: discord.TextChannel | None = None,
        welcome: discord.TextChannel | None = None,
        tickets: discord.CategoryChannel | None = None,
        backup: discord.TextChannel | None = None,
        prefix: str | None = None,
    ) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        setup_data = settings.get("setup", {})
        if logs:
            await self.bot.db.set_settings_value(interaction.guild_id, "logs_channel", logs.id, self.bot.settings.default_prefix)
            setup_data["logs_channel"] = logs.id
        if welcome:
            welcome_data = settings.get("welcome", {})
            welcome_data["channel_id"] = welcome.id
            await self.bot.db.set_settings_value(interaction.guild_id, "welcome", welcome_data, self.bot.settings.default_prefix)
            setup_data["welcome_channel"] = welcome.id
        if tickets:
            setup_data["ticket_category"] = tickets.id
        if backup:
            setup_data["backup_channel"] = backup.id
            await self.bot.db.set_settings_value(interaction.guild_id, "sync_announce_channel", backup.id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(interaction.guild_id, "setup", setup_data, self.bot.settings.default_prefix)
        if prefix:
            await self.bot.db.set_prefix(interaction.guild_id, prefix[:12], self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Setup Saved")
        e.add_field(name="Logs", value=logs.mention if logs else "No change", inline=True)
        e.add_field(name="Welcome", value=welcome.mention if welcome else "No change", inline=True)
        e.add_field(name="Tickets", value=tickets.name if tickets else "No change", inline=True)
        e.add_field(name="Backup/Updates", value=backup.mention if backup else "No change", inline=True)
        e.add_field(name="Prefix", value=f"`{prefix[:12]}`" if prefix else "No change", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @setup.command(name="template", description="Paste a ready-made layout for a server type")
    @app_commands.choices(server_type=[
        app_commands.Choice(name="Community", value="community"),
        app_commands.Choice(name="Gaming", value="gaming"),
        app_commands.Choice(name="Music / Artist", value="music"),
        app_commands.Choice(name="Creator / Streamer", value="creator"),
        app_commands.Choice(name="Business", value="business"),
        app_commands.Choice(name="Marketplace", value="marketplace"),
        app_commands.Choice(name="Product Support", value="support"),
        app_commands.Choice(name="Roleplay", value="roleplay"),
        app_commands.Choice(name="Esports Team", value="esports"),
        app_commands.Choice(name="Study / School", value="study"),
    ])
    @app_admin()
    async def setup_template(self, interaction: discord.Interaction, server_type: app_commands.Choice[str]) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Run this command inside a Discord server.", ephemeral=True)
            return
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
            await interaction.followup.send("I need Manage Channels and Manage Roles to paste a server template.", ephemeral=True)
            return
        template = SERVER_TEMPLATES.get(server_type.value)
        if template is None:
            await interaction.followup.send("That template is not available.", ephemeral=True)
            return

        roles: dict[str, discord.Role] = {}
        for role_name in template["roles"]:
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                permissions = discord.Permissions.none()
                if role_name in {"Moderator", "Support Team"}:
                    permissions = discord.Permissions(manage_messages=True, moderate_members=True)
                elif role_name in {"Support Lead"}:
                    permissions = discord.Permissions(manage_messages=True, moderate_members=True, view_audit_log=True)
                role = await guild.create_role(name=role_name, permissions=permissions, reason=f"{template['label']} template")
            roles[role_name] = role

        verified_role = roles.get("Verified") or discord.utils.get(guild.roles, name="Verified")
        if verified_role is None:
            verified_role = await guild.create_role(name="Verified", reason=f"{template['label']} template")
            roles["Verified"] = verified_role

        created_channels: dict[str, discord.abc.GuildChannel] = {}
        created_count = 0
        for category_name, channel_names in template["categories"].items():
            category = discord.utils.get(guild.categories, name=category_name)
            if category is None:
                category = await guild.create_category(category_name, reason=f"{template['label']} template")
                created_count += 1
            for channel_name in channel_names:
                if category_name == "VOICE":
                    channel = discord.utils.get(category.voice_channels, name=channel_name)
                    if channel is None:
                        channel = await guild.create_voice_channel(channel_name, category=category, reason=f"{template['label']} template")
                        created_count += 1
                else:
                    channel = discord.utils.get(category.text_channels, name=channel_name)
                    if channel is None:
                        channel = await guild.create_text_channel(
                            channel_name,
                            category=category,
                            topic=f"{template['label']} server — {channel_name.replace('-', ' ')}",
                            reason=f"{template['label']} template",
                        )
                        created_count += 1
                created_channels[channel_name] = channel

        read_only_names = {"welcome", "rules", "announcements", "verify", "services", "status", "schedule", "lore", "marketplace-rules", "giveaways"}
        for channel_name in read_only_names:
            channel = created_channels.get(channel_name)
            if isinstance(channel, discord.TextChannel):
                await channel.set_permissions(guild.default_role, send_messages=False, reason="Template information channel")
                await channel.set_permissions(me, view_channel=True, send_messages=True, embed_links=True, reason="AinBot template panels")

        async def post_once(channel_name: str, title: str, description: str, view: discord.ui.View | None = None) -> None:
            channel = created_channels.get(channel_name)
            if not isinstance(channel, discord.TextChannel):
                return
            panel = await self.themed(guild.id, title, description)
            async for message in channel.history(limit=20):
                if message.author.id == me.id and message.embeds and message.embeds[0].title == title:
                    await message.edit(embed=panel, view=view)
                    return
            await channel.send(embed=panel, view=view)

        await post_once("welcome", f"Welcome to {guild.name}", str(template["description"]) + "\n\nRead the rules, verify, choose your roles and join the conversation.")
        await post_once("rules", "Server Rules", "1. Respect members and staff.\n2. No scams, raids, harassment or unwanted advertising.\n3. Keep content in the correct channels.\n4. Do not share passwords, tokens, recovery codes or payment secrets.\n5. Follow Discord's Terms of Service and Community Guidelines.")
        await post_once("announcements", "Announcements", "Official server news, events and important updates will be posted here.")

        from bot.cogs.growth_safety import VerifyView
        growth_cog = self.bot.get_cog("GrowthSafety")
        if growth_cog:
            await self.bot.db.set_settings_value(guild.id, "verify_role", verified_role.id, self.bot.settings.default_prefix)
            await self.bot.db.set_settings_value(guild.id, "verify_min_account_days", 3, self.bot.settings.default_prefix)
            await post_once("verify", "Verify", f"Press the button to receive {verified_role.mention} and unlock member access. Accounts must be at least three days old.", VerifyView(growth_cog))

        from bot.cogs.tickets import TicketView
        await post_once("open-a-ticket", "Support Tickets", "Open a private ticket when you need help. Explain what you need and wait for a staff member.", TicketView())

        welcome_channel = created_channels.get("welcome")
        ticket_channel = created_channels.get("open-a-ticket")
        setup_data = {
            "welcome_channel": welcome_channel.id if isinstance(welcome_channel, discord.TextChannel) else None,
            "ticket_channel": ticket_channel.id if isinstance(ticket_channel, discord.TextChannel) else None,
            "template": server_type.value,
        }
        await self.bot.db.set_settings_value(guild.id, "server_template", setup_data, self.bot.settings.default_prefix)
        result = await self.themed(guild.id, f"{template['label']} Template Ready", f"Added or refreshed the layout and starter panels. `{created_count}` categories/channels were newly created. Existing channels were kept.")
        await interaction.followup.send(embed=result, ephemeral=True)

    @setup.command(name="bot_community", description="Build a compact AinBot promotion and support server")
    async def setup_bot_community(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("Run this command inside a Discord server.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and not await self.bot.is_owner(interaction.user):
            await interaction.followup.send("Only a server administrator or configured bot owner can build the community server.", ephemeral=True)
            return
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
            await interaction.followup.send("I need Manage Channels and Manage Roles before I can build the server.", ephemeral=True)
            return

        role_specs = [
            ("AinBot Owner", discord.Permissions(administrator=True)),
            ("Bot Developer", discord.Permissions(manage_guild=True, manage_channels=True, manage_roles=True, view_audit_log=True)),
            ("Support Lead", discord.Permissions(manage_messages=True, moderate_members=True, view_audit_log=True)),
            ("Support Team", discord.Permissions(manage_messages=True)),
            ("Moderator", discord.Permissions(manage_messages=True, moderate_members=True, kick_members=True)),
            ("Partner", discord.Permissions.none()),
            ("Premium", discord.Permissions.none()),
            ("Verified", discord.Permissions.none()),
            ("Server Booster", discord.Permissions.none()),
            ("Giveaway Ping", discord.Permissions.none()),
            ("Update Ping", discord.Permissions.none()),
            ("Bots", discord.Permissions.none()),
            ("Muted", discord.Permissions.none()),
        ]
        roles: dict[str, discord.Role] = {}
        for name, permissions in role_specs:
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                role = await guild.create_role(name=name, permissions=permissions, reason="AinBot community setup")
            roles[name] = role

        everyone = guild.default_role
        staff_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            roles["AinBot Owner"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Bot Developer"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Lead"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Team"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Moderator"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        premium_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            roles["Premium"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["AinBot Owner"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Team"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        verified_overwrites = {
            everyone: discord.PermissionOverwrite(view_channel=False),
            roles["Verified"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            roles["AinBot Owner"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Bot Developer"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Lead"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Support Team"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            roles["Moderator"]: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }

        async def category(name: str, overwrites: dict | None = None) -> discord.CategoryChannel:
            found = discord.utils.get(guild.categories, name=name)
            if found:
                if overwrites is not None:
                    await found.edit(overwrites=overwrites, reason="Refresh AinBot community access")
                return found
            return await guild.create_category(name, overwrites=overwrites or {}, reason="AinBot community setup")

        async def text_channel(cat: discord.CategoryChannel, name: str, topic: str, read_only: bool = False) -> discord.TextChannel:
            found = discord.utils.get(cat.text_channels, name=name)
            if found:
                await found.edit(topic=topic, sync_permissions=not read_only, reason="Refresh AinBot community channel")
                if read_only:
                    await found.set_permissions(everyone, view_channel=None, send_messages=False, reason="AinBot read-only panel")
                    await found.set_permissions(me, view_channel=True, send_messages=True, reason="AinBot panel access")
                return found
            overwrites = None
            if read_only:
                overwrites = {everyone: discord.PermissionOverwrite(send_messages=False), me: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
            return await guild.create_text_channel(name, category=cat, topic=topic, overwrites=overwrites or {}, reason="AinBot community setup")

        start = await category("START HERE")
        bot_hub = await category("AINBOT", verified_overwrites)
        community = await category("COMMUNITY", verified_overwrites)
        support = await category("SUPPORT", verified_overwrites)
        premium = await category("PREMIUM", premium_overwrites)
        staff = await category("STAFF", staff_overwrites)
        voice = await category("VOICE")

        welcome = await text_channel(start, "welcome", "Start here for AinBot information and community access.", True)
        rules = await text_channel(start, "rules", "Community rules and Discord requirements.", True)
        verify = await text_channel(start, "verify", "Account verification and member access.", True)
        announcements = await text_channel(bot_hub, "announcements", "Official AinBot announcements.", True)
        updates = await text_channel(bot_hub, "updates", "AinBot updates, fixes, and release notes.", True)
        status = await text_channel(bot_hub, "status", "Live service and incident updates.", True)
        commands_channel = await text_channel(bot_hub, "commands", "Command list and usage information.", True)
        invite = await text_channel(bot_hub, "invite-ainbot", "Invite and authorization links for AinBot.", True)
        general = await text_channel(community, "general", "Main AinBot community chat.")
        media = await text_channel(community, "media", "Share screenshots, clips, art, and community media.")
        showcase = await text_channel(community, "showcase", "Show server setups, themes, and AinBot results.")
        suggestions = await text_channel(community, "suggestions", "Suggest new AinBot features and improvements.")
        partnerships = await text_channel(community, "partnerships", "Approved community and creator partnerships.", True)
        giveaways = await text_channel(community, "giveaways", "Official AinBot community giveaways.", True)
        faq = await text_channel(support, "faq", "Common setup and troubleshooting answers.", True)
        tickets = await text_channel(support, "open-a-ticket", "Open a private support ticket here.", True)
        bug_reports = await text_channel(support, "bug-reports", "Report reproducible AinBot problems and include the command used.")
        premium_chat = await text_channel(premium, "premium-chat", "Private chat for AinBot Premium members.")
        premium_support = await text_channel(premium, "premium-support", "Priority support for Premium members.")
        staff_chat = await text_channel(staff, "staff-chat", "Private staff coordination.")
        staff_logs = await text_channel(staff, "bot-logs", "Private AinBot and moderation logs.")
        payment_logs = await text_channel(staff, "payment-logs", "Private purchase and fulfillment notices.")

        if discord.utils.get(voice.voice_channels, name="Community VC") is None:
            await guild.create_voice_channel("Community VC", category=voice, reason="AinBot community setup")
        if discord.utils.get(voice.voice_channels, name="Support Waiting") is None:
            await guild.create_voice_channel("Support Waiting", category=voice, reason="AinBot community setup")
        if discord.utils.get(voice.voice_channels, name="Premium VC") is None:
            await guild.create_voice_channel("Premium VC", category=premium, overwrites=premium_overwrites, reason="AinBot community setup")

        stats_category = await category("LIVE STATS", verified_overwrites)
        stats_ids: dict[str, int] = {}
        for label in ("Members", "In VC", "Top Balance", "MVP Winner", "Giveaway Winner"):
            prefix = f"{label}:"
            channel = next((item for item in stats_category.voice_channels if item.name.startswith(prefix)), None)
            if channel is None:
                channel = await guild.create_voice_channel(f"{label}: 0", category=stats_category, reason="AinBot community setup")
            await channel.set_permissions(everyone, connect=False)
            stats_ids[label.lower()] = channel.id

        await self.bot.db.set_settings_value(guild.id, "logs_channel", staff_logs.id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "welcome", {"channel_id": welcome.id, "message": "Welcome {mention} to the official AinBot community."}, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "verify_role", roles["Verified"].id, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "verify_min_account_days", 3, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "stats_channels", stats_ids, self.bot.settings.default_prefix)
        await self.bot.db.set_settings_value(guild.id, "setup", {"logs_channel": staff_logs.id, "welcome_channel": welcome.id, "ticket_category": support.id, "backup_channel": updates.id, "payment_logs_channel": payment_logs.id}, self.bot.settings.default_prefix)

        async def post_once(channel: discord.TextChannel, title: str, description: str, view: discord.ui.View | None = None) -> None:
            panel = await self.themed(guild.id, title, description)
            async for message in channel.history(limit=30):
                if message.author.id == me.id and message.embeds and message.embeds[0].title == title:
                    await message.edit(embed=panel, view=view)
                    return
            await channel.send(embed=panel, view=view)

        from bot.cogs.tickets import TicketView
        from bot.cogs.growth_safety import VerifyView

        growth_cog = self.bot.get_cog("GrowthSafety")
        verify_view: discord.ui.View | None = VerifyView(growth_cog) if growth_cog else None
        public_domain = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not public_domain:
            railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
            public_domain = f"https://{railway_domain}" if railway_domain else ""
        if verify_view and public_domain.startswith(("https://", "http://")):
            verify_view.add_item(discord.ui.Button(label="Authorize AinBot", style=discord.ButtonStyle.link, url=f"{public_domain}/oauth/discord/start"))

        client_id = getattr(self.bot.user, "id", 0)
        invite_url = discord.utils.oauth_url(client_id, permissions=discord.Permissions(
            view_channel=True, send_messages=True, embed_links=True, read_message_history=True,
            manage_messages=True, manage_channels=True, manage_roles=True, moderate_members=True,
            kick_members=True, ban_members=True, move_members=True, connect=True, speak=True,
        ))
        invite_view = discord.ui.View(timeout=None)
        invite_view.add_item(discord.ui.Button(label="Add AinBot", style=discord.ButtonStyle.link, url=invite_url))
        if public_domain.startswith(("https://", "http://")):
            invite_view.add_item(discord.ui.Button(label="Authorize Account", style=discord.ButtonStyle.link, url=f"{public_domain}/oauth/discord/start"))

        await post_once(welcome, "Welcome to AinBot", "AinBot is built for active communities that need moderation, defense, temporary voice channels, tickets, giveaways, economy, music and clean server management. Start in the verification channel, then explore the server.")
        await post_once(rules, "Community Rules", "1. Respect members and staff.\n2. No scams, credential requests, raids, or abuse.\n3. No unsolicited advertising or mass mentions.\n4. Use tickets for private support and never post tokens, passwords, payment details or OAuth secrets.\n5. Follow Discord's Terms of Service and Community Guidelines.")
        await post_once(verify, "Get Verified", "Press **Verify** to unlock the community. Accounts must be at least three days old. The optional authorization button connects your Discord account to AinBot for Discord-approved member transfer; it never asks for your password.", verify_view)
        await post_once(announcements, "Official Announcements", "Product news, community announcements and important service notices are posted here.")
        await post_once(updates, "AinBot Updates", "New commands, improvements and fixes will be posted here with clear setup notes.")
        await post_once(status, "Service Status", "AinBot is online. If a command fails, run `/doctor` and open a support ticket with the result.")
        await post_once(commands_channel, "AinBot Commands", "Run `/help` for the full command menu. Use `/doctor` for permission and configuration checks, `/setup wizard` for server setup, `/setup jtc` for temporary voice channels, and `/lock all` during a server-wide incident.")
        await post_once(invite, "Add AinBot", "Add AinBot to a server you manage. Discord will show every requested permission before you approve it. Account authorization is optional and is only used for features that require explicit consent.", invite_view)
        await post_once(partnerships, "Partnerships", "Approved creators and communities are featured here. Open a ticket with your server invite, member count, activity level and what you want to build with AinBot.")
        await post_once(giveaways, "Community Giveaways", "Official giveaways are posted here. AinBot staff will never request payment, a password, token or recovery code to release a prize.")
        await post_once(faq, "Quick Answers", "**Bot not responding?** Run `/doctor`.\n**Need server setup?** Run `/setup wizard`.\n**Need temporary voice channels?** Run `/setup jtc`.\n**Need private help?** Use the ticket panel.\n**Need the bot invite?** Visit the invite channel.")
        await post_once(tickets, "AinBot Support", "Open a private ticket for setup, billing or technical support. Include the command you used and what happened. Never send passwords, bot tokens or payment secrets.", TicketView())

        stats_cog = self.bot.get_cog("GrowthSafety")
        if stats_cog and hasattr(stats_cog, "update_stats"):
            await stats_cog.update_stats(guild)

        await interaction.followup.send(embed=await self.themed(guild.id, "AinBot Community Ready", f"The compact community layout, roles, verification gate, support panel, invite buttons, OAuth authorization link and live statistics are ready.\n\nMembers start in {verify.mention}. Support opens in {tickets.mention}."), ephemeral=True)

    @dashboard.command(name="overview", description="Show all major bot modules and setup status")
    @app_admin()
    async def dashboard_overview(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Bot Dashboard")
        e.add_field(name="Prefix", value=f"`{settings.get('prefix', self.bot.settings.default_prefix)}`", inline=True)
        e.add_field(name="Anti-Nuke", value="On" if settings.get("antinuke_enabled", settings.get("antinuke_v2", {}).get("enabled", True)) else "Off", inline=True)
        e.add_field(name="Music", value="On" if getattr(self.bot.settings, "enable_music", True) else "Off", inline=True)
        e.add_field(name="JTC Lobbies", value=f"`{len(settings.get('jtc_templates', {}))}`", inline=True)
        e.add_field(name="Welcome", value="Set" if settings.get("welcome", {}).get("channel_id") else "Not set", inline=True)
        e.add_field(name="Logs", value=f"<#{settings.get('logs_channel')}>" if settings.get("logs_channel") else "Not set", inline=True)
        e.add_field(name="Theme", value="Set" if settings.get("theme") else "Default", inline=True)
        e.add_field(name="Backup", value="Webhook set" if getattr(self.bot.settings, "backup_webhook_url", None) else "No webhook", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @dashboard.command(name="post", description="Post a clean public bot dashboard")
    @app_admin()
    async def dashboard_post(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        target = channel or interaction.channel
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        e = await self.themed(interaction.guild_id, "Server Bot Dashboard", "Current bot systems and quick status.")
        e.add_field(name="Commands", value=f"`{len(self.bot.tree.get_commands())}` slash groups loaded", inline=True)
        e.add_field(name="Prefix", value=f"`{settings.get('prefix', self.bot.settings.default_prefix)}`", inline=True)
        e.add_field(name="Status", value="Online", inline=True)
        e.add_field(name="Useful Checks", value="Run `/doctor` if anything stops working.", inline=False)
        await target.send(embed=e)
        await interaction.response.send_message(embed=await self.themed(interaction.guild_id, "Dashboard Posted"), ephemeral=True)

    @scan.command(name="perms", description="Scan dangerous roles and members")
    @app_admin()
    async def scan_perms(self, interaction: discord.Interaction) -> None:
        dangerous_roles = []
        for role in sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True):
            hits = [name for name in DANGEROUS_PERMS if getattr(role.permissions, name)]
            if hits and not role.is_default():
                dangerous_roles.append(f"{role.mention} - `{', '.join(hits[:4])}`")
        dangerous_members = []
        for member in interaction.guild.members:
            if member.bot:
                continue
            hits = [name for name in DANGEROUS_PERMS if getattr(member.guild_permissions, name)]
            if hits:
                dangerous_members.append(f"{member.mention} - `{', '.join(hits[:4])}`")
        e = await self.themed(interaction.guild_id, "Permission Scan")
        e.add_field(name="Dangerous Roles", value="\n".join(dangerous_roles[:15])[:1024] or "None found.", inline=False)
        e.add_field(name="Dangerous Members", value="\n".join(dangerous_members[:15])[:1024] or "None found.", inline=False)
        e.set_footer(text="Only the first 15 of each list are shown.")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="checkperms", description="Check what permissions the bot is missing in a channel")
    @app_admin()
    async def checkperms(self, interaction: discord.Interaction, channel: discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel | None = None) -> None:
        target = channel or interaction.channel
        me = interaction.guild.me
        perms = target.permissions_for(me)
        required = {
            "view_channel": "View Channel",
            "send_messages": "Send Messages",
            "embed_links": "Embed Links",
            "manage_messages": "Manage Messages",
            "manage_channels": "Manage Channels",
            "connect": "Connect",
            "speak": "Speak",
            "move_members": "Move Members",
        }
        lines = []
        for attr, label in required.items():
            value = getattr(perms, attr, False)
            lines.append(f"`{'OK' if value else 'FIX'}` **{label}**")
        e = await self.themed(interaction.guild_id, "Channel Permission Check", f"Target: {target.mention if hasattr(target, 'mention') else target.name}")
        e.add_field(name="Needed Permissions", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.command(name="setupwizard", aliases=["setup"])
    @has_guild_permissions(manage_guild=True)
    async def prefix_setupwizard(self, ctx: commands.Context) -> None:
        e = await self.themed(ctx.guild.id, "Setup Wizard", "Use `/setup wizard` for the clickable setup form.\nUse `/setup jtc` for join-to-create setup.\nUse `/dashboard overview` to check the bot.")
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="checkperms")
    @has_guild_permissions(manage_guild=True)
    async def prefix_checkperms(self, ctx: commands.Context) -> None:
        me = ctx.guild.me
        perms = ctx.channel.permissions_for(me)
        lines = [
            f"`{'OK' if perms.view_channel else 'FIX'}` **View Channel**",
            f"`{'OK' if perms.send_messages else 'FIX'}` **Send Messages**",
            f"`{'OK' if perms.embed_links else 'FIX'}` **Embed Links**",
            f"`{'OK' if perms.manage_messages else 'FIX'}` **Manage Messages**",
        ]
        e = await self.themed(ctx.guild.id, "Channel Permission Check")
        e.add_field(name="Needed Permissions", value="\n".join(lines), inline=False)
        await ctx.reply(embed=e, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupTools(bot))
