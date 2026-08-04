from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, configured_owner
from bot.core.utils import embed


class JoinToCreate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.owners: dict[int, int] = {}

    jtc = app_commands.Group(name="jtc", description="Join-to-create voice channels")

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
        if self.owners[member.voice.channel.id] != member.id and not member.guild_permissions.manage_channels and not await configured_owner(self.bot, member):
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
                await channel.set_permissions(member, manage_channels=True, connect=True, view_channel=True)
                await member.move_to(channel)
                try:
                    await channel.send(embed=embed(
                        "VC Controls",
                        "\n".join([
                            "`/vc claim` - claim this channel",
                            "`/vc rename` - rename it",
                            "`/vc lock` / `/vc unlock` - control access",
                            "`/vc hide` / `/vc reveal` - visibility",
                            "`/vc limit` - set user limit",
                            "`/vc permit` / `/vc reject` - allow or block users",
                            "`/vc transfer` - give ownership",
                            "`-vc leaderboard` - show VC time leaderboard",
                            "`-vc stfu @user` - trusted mute lock toggle",
                        ]),
                    ))
                except discord.HTTPException:
                    pass
        if before.channel and before.channel.id in self.owners and not before.channel.members:
            self.owners.pop(before.channel.id, None)
            await before.channel.delete(reason="Empty join-to-create channel")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(JoinToCreate(bot))
