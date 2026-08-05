from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin
from bot.core.utils import embed


class JtcRenameModal(discord.ui.Modal):
    def __init__(self, cog: "JoinToCreate", channel: discord.VoiceChannel) -> None:
        super().__init__(title="Rename Voice Channel")
        self.cog = cog
        self.channel = channel
        self.name_input = discord.ui.TextInput(label="New name", default=channel.name, max_length=90)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.cog.can_control(interaction, self.channel):
            return
        await self.channel.edit(name=str(self.name_input)[:90], reason=f"JTC rename by {interaction.user}")
        await interaction.response.send_message("Voice channel renamed.", ephemeral=True)


class JtcLimitModal(discord.ui.Modal):
    def __init__(self, cog: "JoinToCreate", channel: discord.VoiceChannel) -> None:
        super().__init__(title="Set User Limit")
        self.cog = cog
        self.channel = channel
        self.limit_input = discord.ui.TextInput(label="Limit", placeholder="0 for unlimited", default=str(channel.user_limit), max_length=2)
        self.add_item(self.limit_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.cog.can_control(interaction, self.channel):
            return
        try:
            limit = max(0, min(99, int(str(self.limit_input))))
        except ValueError:
            await interaction.response.send_message("Use a number from 0 to 99.", ephemeral=True)
            return
        await self.channel.edit(user_limit=limit, reason=f"JTC limit by {interaction.user}")
        await interaction.response.send_message(f"User limit set to `{limit}`.", ephemeral=True)


class JtcControlView(discord.ui.View):
    def __init__(self, cog: "JoinToCreate", channel_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id

    async def channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return None
        channel = interaction.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("That temp voice channel is gone.", ephemeral=True)
            return None
        return channel

    @discord.ui.button(label="Claim", emoji="👑", style=discord.ButtonStyle.primary)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        self.cog.owners[channel.id] = interaction.user.id
        await self.cog.save_temp_owner(channel.guild, channel.id, interaction.user.id)
        await channel.set_permissions(interaction.user, manage_channels=True, connect=True, view_channel=True)
        await interaction.response.send_message(f"{interaction.user.mention} now owns this VC.", ephemeral=True)

    @discord.ui.button(label="Rename", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcRenameModal(self.cog, channel))

    @discord.ui.button(label="Limit", emoji="👥", style=discord.ButtonStyle.secondary)
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None:
            return
        if not await self.cog.can_control(interaction, channel, respond=False):
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(JtcLimitModal(self.cog, channel))

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.danger)
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=False)
        await interaction.response.send_message("Voice channel locked.", ephemeral=True)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.success)
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, connect=None)
        await interaction.response.send_message("Voice channel unlocked.", ephemeral=True)

    @discord.ui.button(label="Hide", emoji="🙈", style=discord.ButtonStyle.secondary)
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=False)
        await interaction.response.send_message("Voice channel hidden.", ephemeral=True)

    @discord.ui.button(label="Reveal", emoji="👁️", style=discord.ButtonStyle.secondary)
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel = await self.channel(interaction)
        if channel is None or not await self.cog.can_control(interaction, channel):
            return
        await channel.set_permissions(channel.guild.default_role, view_channel=None)
        await interaction.response.send_message("Voice channel revealed.", ephemeral=True)


class JoinToCreate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.owners: dict[int, int] = {}
        self.cleanup_empty_jtc_channels.start()

    def cog_unload(self) -> None:
        self.cleanup_empty_jtc_channels.cancel()

    jtc = app_commands.Group(name="jtc", description="Join-to-create voice channels")

    async def save_temp_owner(self, guild: discord.Guild, channel_id: int, owner_id: int) -> None:
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        temp_channels = settings.get("jtc_temp_channels", {})
        data = temp_channels.setdefault(str(channel_id), {})
        data["owner_id"] = owner_id
        await self.bot.db.set_settings_value(guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)

    async def can_control(self, interaction: discord.Interaction, channel: discord.VoiceChannel, respond: bool = True) -> bool:
        if not isinstance(interaction.user, discord.Member):
            if respond:
                await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return False
        settings = await self.bot.db.get_settings(channel.guild.id, self.bot.settings.default_prefix)
        saved = settings.get("jtc_temp_channels", {}).get(str(channel.id), {})
        owner_id = self.owners.get(channel.id) or saved.get("owner_id")
        if owner_id == interaction.user.id or interaction.user.guild_permissions.manage_channels:
            return True
        if respond:
            await interaction.response.send_message("Only the VC owner or moderators can use this.", ephemeral=True)
        return False

    def control_embed(self, channel: discord.VoiceChannel, owner: discord.Member) -> discord.Embed:
        e = embed("Voice Control Panel", f"Owner: {owner.mention}\nUse the buttons below to control {channel.mention}.")
        e.add_field(name="Quick Controls", value="Claim, rename, set user limit, lock, unlock, hide, or reveal this temporary VC.", inline=False)
        e.set_footer(text="This panel stays with the temp VC and deletes when the VC is empty.")
        return e

    async def send_control_panel(self, channel: discord.VoiceChannel, owner: discord.Member) -> None:
        try:
            await channel.send(content=owner.mention, embed=self.control_embed(channel, owner), view=JtcControlView(self, channel.id))
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=45)
    async def cleanup_empty_jtc_channels(self) -> None:
        for guild in self.bot.guilds:
            settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
            temp_channels = settings.get("jtc_temp_channels", {})
            changed = False
            for channel_id in list(temp_channels):
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    temp_channels.pop(channel_id, None)
                    self.owners.pop(int(channel_id), None)
                    changed = True
                    continue
                if isinstance(channel, discord.VoiceChannel) and not channel.members:
                    temp_channels.pop(channel_id, None)
                    self.owners.pop(channel.id, None)
                    changed = True
                    await channel.delete(reason="Empty join-to-create channel")
            if changed:
                await self.bot.db.set_settings_value(guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)

    @cleanup_empty_jtc_channels.before_loop
    async def before_cleanup_empty_jtc_channels(self) -> None:
        await self.bot.wait_until_ready()

    @jtc.command(name="setup", description="Set a voice channel as a join-to-create template")
    @app_admin()
    async def setup_template(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
        name: str = "{user}'s room",
        user_limit: int = 0,
        output_category: discord.CategoryChannel | None = None,
    ) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        templates[str(channel.id)] = {
            "name": name,
            "user_limit": user_limit,
            "category_id": output_category.id if output_category else None,
        }
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", templates, self.bot.settings.default_prefix)
        await interaction.response.send_message("Join-to-create template saved.", ephemeral=True)

    @jtc.command(name="category", description="Set where temporary JTC voice channels are created")
    @app_admin()
    async def category(self, interaction: discord.Interaction, lobby: discord.VoiceChannel, output_category: discord.CategoryChannel) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        template = templates.setdefault(str(lobby.id), {"name": "{user}'s room", "user_limit": 0})
        template["category_id"] = output_category.id
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", templates, self.bot.settings.default_prefix)
        await interaction.response.send_message(f"Temporary channels from {lobby.mention} will be created in **{output_category.name}**.", ephemeral=True)

    @jtc.command(name="config", description="Show current join-to-create setup")
    @app_admin()
    async def config(self, interaction: discord.Interaction) -> None:
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        templates = settings.get("jtc_templates", {})
        e = embed("JTC Config")
        if not templates:
            e.description = "Join-to-create is not configured yet."
        for channel_id, template in templates.items():
            lobby = interaction.guild.get_channel(int(channel_id))
            category = interaction.guild.get_channel(template.get("category_id") or 0)
            template_name = template.get("name", "{user}'s room")
            e.add_field(
                name=lobby.mention if lobby else f"Missing lobby `{channel_id}`",
                value=(
                    f"Name: `{template_name}`\n"
                    f"User limit: `{template.get('user_limit', 0)}`\n"
                    f"Output category: `{category.name if isinstance(category, discord.CategoryChannel) else 'Same as lobby'}`"
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @jtc.command(name="disable", description="Disable join-to-create")
    @app_admin()
    async def disable(self, interaction: discord.Interaction) -> None:
        await self.bot.db.set_settings_value(interaction.guild_id, "jtc_templates", {}, self.bot.settings.default_prefix)
        await interaction.response.send_message("Join-to-create disabled.", ephemeral=True)

    @jtc.command(name="claim", description="Claim the current temporary voice channel")
    async def claim(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Join your temporary channel first.", ephemeral=True)
            return
        channel = member.voice.channel
        if channel.id not in self.owners:
            await interaction.response.send_message("This is not a managed temporary channel.", ephemeral=True)
            return
        self.owners[channel.id] = member.id
        await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
        await interaction.response.send_message("You now own this channel.", ephemeral=True)

    @jtc.command(name="rename", description="Rename your temporary voice channel")
    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or member.voice.channel.id not in self.owners:
            await interaction.response.send_message("Join your temporary channel first.", ephemeral=True)
            return
        if self.owners[member.voice.channel.id] != member.id and not member.guild_permissions.manage_channels:
            await interaction.response.send_message("Only the owner or moderators can rename this channel.", ephemeral=True)
            return
        await member.voice.channel.edit(name=name[:90])
        await interaction.response.send_message("Channel renamed.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if after.channel:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            template = settings.get("jtc_templates", {}).get(str(after.channel.id))
            if template:
                category = member.guild.get_channel(template.get("category_id") or 0)
                if not isinstance(category, discord.CategoryChannel):
                    category = after.channel.category
                channel = await member.guild.create_voice_channel(
                    template.get("name", "{user}'s room").format(user=member.display_name)[:90],
                    category=category,
                    user_limit=int(template.get("user_limit", 0)),
                    reason="Join-to-create",
                )
                self.owners[channel.id] = member.id
                temp_channels = settings.get("jtc_temp_channels", {})
                temp_channels[str(channel.id)] = {"owner_id": member.id, "lobby_id": after.channel.id}
                await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
                await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
                await member.move_to(channel)
                await self.send_control_panel(channel, member)
        if before.channel and not before.channel.members:
            settings = await self.bot.db.get_settings(member.guild.id, self.bot.settings.default_prefix)
            temp_channels = settings.get("jtc_temp_channels", {})
            is_temp_channel = before.channel.id in self.owners or str(before.channel.id) in temp_channels
            if not is_temp_channel:
                return
            self.owners.pop(before.channel.id, None)
            temp_channels.pop(str(before.channel.id), None)
            await self.bot.db.set_settings_value(member.guild.id, "jtc_temp_channels", temp_channels, self.bot.settings.default_prefix)
            await before.channel.delete(reason="Empty join-to-create channel")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JoinToCreate(bot))
