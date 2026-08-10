from __future__ import annotations

import io

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed


class TicketView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        settings = await interaction.client.db.get_settings(guild.id, interaction.client.settings.default_prefix)
        ticket_cfg = settings.get("ticket_system", {})
        category = guild.get_channel(int(ticket_cfg.get("category_id", 0) or 0))
        if not isinstance(category, discord.CategoryChannel):
            category = None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}"[:90], category=category, overwrites=overwrites, reason="Ticket opened")
        await interaction.client.db.execute("INSERT OR REPLACE INTO tickets(channel_id,guild_id,opener_id) VALUES(?,?,?)", channel.id, guild.id, interaction.user.id)
        await channel.send(embed=embed("Ticket", f"{interaction.user.mention}, staff will be with you soon."), view=TicketManageView())
        await interaction.response.send_message(f"Opened {channel.mention}.", ephemeral=True)


class TicketManageView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.secondary, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.client.db.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", interaction.user.id, interaction.channel_id)
        await interaction.response.send_message(f"Claimed by {interaction.user.mention}.")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        rows = []
        async for msg in interaction.channel.history(limit=500, oldest_first=True):
            rows.append(f"[{msg.created_at:%Y-%m-%d %H:%M}] {msg.author}: {msg.clean_content}")
        data = "\n".join(rows).encode("utf-8")
        settings = await interaction.client.db.get_settings(interaction.guild_id, interaction.client.settings.default_prefix)
        ticket_cfg = settings.get("ticket_system", {})
        log_channel = interaction.guild.get_channel(int(ticket_cfg.get("log_channel_id", 0) or 0))
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(
                embed=await interaction.client.themed_embed(interaction.guild_id, "Ticket Closed", f"Channel: `{interaction.channel.name}`\nClosed by: {interaction.user.mention}"),
                file=discord.File(io.BytesIO(data), filename=f"{interaction.channel.name}-transcript.txt"),
            )
        await interaction.response.send_message("Transcript saved. Closing ticket.", ephemeral=True)
        await interaction.client.db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", interaction.channel_id)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.add_view(TicketView())
        bot.add_view(TicketManageView())

    ticket = app_commands.Group(name="ticket", description="Ticket system")

    @ticket.command(name="setup", description="Set ticket category and permanent transcript log channel")
    @app_admin()
    async def setup_ticket_system(self, interaction: discord.Interaction, category: discord.CategoryChannel, transcript_logs: discord.TextChannel) -> None:
        await self.bot.db.set_settings_value(
            interaction.guild_id,
            "ticket_system",
            {"category_id": category.id, "log_channel_id": transcript_logs.id},
            self.bot.settings.default_prefix,
        )
        await interaction.response.send_message(f"Tickets will open in **{category.name}** and transcripts will be saved in {transcript_logs.mention}.", ephemeral=True)

    @ticket.command(name="panel", description="Post a ticket panel")
    @app_admin()
    async def panel(self, interaction: discord.Interaction, title: str = "Support Tickets", description: str = "Open a ticket for private support.") -> None:
        await interaction.channel.send(embed=embed(title, description), view=TicketView())
        await interaction.response.send_message("Ticket panel posted.", ephemeral=True)

    @ticket.command(name="create", description="Create a private support ticket")
    async def create(self, interaction: discord.Interaction, reason: str = "Support") -> None:
        guild = interaction.guild
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        ticket_cfg = settings.get("ticket_system", {})
        category = guild.get_channel(int(ticket_cfg.get("category_id", 0) or 0))
        if not isinstance(category, discord.CategoryChannel):
            category = None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}"[:90], category=category, overwrites=overwrites, reason=reason)
        await self.bot.db.execute("INSERT OR REPLACE INTO tickets(channel_id,guild_id,opener_id) VALUES(?,?,?)", channel.id, guild.id, interaction.user.id)
        await channel.send(embed=embed("Ticket", f"{interaction.user.mention}, staff will be with you soon."), view=TicketManageView())
        await interaction.response.send_message(f"Opened {channel.mention}.", ephemeral=True)

    @ticket.command(name="close", description="Close this ticket channel")
    async def close(self, interaction: discord.Interaction) -> None:
        row = await self.bot.db.fetchrow("SELECT channel_id FROM tickets WHERE channel_id=? AND status='open'", interaction.channel_id)
        if row is None:
            await interaction.response.send_message("This is not an open ticket.", ephemeral=True)
            return
        rows = []
        async for message in interaction.channel.history(limit=500, oldest_first=True):
            rows.append(f"[{message.created_at:%Y-%m-%d %H:%M}] {message.author}: {message.clean_content}")
        data = "\n".join(rows).encode("utf-8")
        settings = await self.bot.db.get_settings(interaction.guild_id, self.bot.settings.default_prefix)
        log_channel = interaction.guild.get_channel(int(settings.get("ticket_system", {}).get("log_channel_id", 0) or 0))
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(embed=await self.bot.themed_embed(interaction.guild_id, "Ticket Closed", f"Channel: `{interaction.channel.name}`\nClosed by: {interaction.user.mention}"), file=discord.File(io.BytesIO(data), filename=f"{interaction.channel.name}-transcript.txt"))
        await self.bot.db.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", interaction.channel_id)
        await interaction.response.send_message("Transcript saved. Closing ticket.", ephemeral=True)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")

    @ticket.command(name="add", description="Add a member to this ticket")
    async def add(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"Added {member.mention}.", ephemeral=True)

    @ticket.command(name="remove", description="Remove a member from this ticket")
    async def remove(self, interaction: discord.Interaction, member: discord.Member) -> None:
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"Removed {member.mention}.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
