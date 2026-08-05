from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.core.checks import app_admin
from bot.core.utils import embed


class JoinToCreate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.owners: dict[int, int] = {}
        self.cleanup_empty_jtc_channels.start()

    def cog_unload(self) -> None:
        self.cleanup_empty_jtc_channels.cancel()

    jtc = app_commands.Group(name="jtc", description="Join-to-create voice channels")

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
