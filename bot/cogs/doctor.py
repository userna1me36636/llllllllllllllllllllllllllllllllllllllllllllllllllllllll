from __future__ import annotations

import os
import shutil

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin, has_guild_permissions
from bot.core.utils import embed, style_embed, theme_color_from_data


class Doctor(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def theme(self, guild_id: int | None) -> tuple[discord.Color, dict]:
        color = discord.Color.from_rgb(170, 22, 38)
        theme: dict = {}
        if guild_id is None:
            return color, theme
        try:
            settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
            theme = settings.get("theme", {})
            color = theme_color_from_data(theme, color)
        except Exception:
            pass
        return color, theme

    @staticmethod
    def line(ok: bool, label: str, fix: str = "") -> str:
        state = "OK" if ok else "FIX"
        return f"`{state}` **{label}**" + (f"\n{fix}" if fix and not ok else "")

    @staticmethod
    def optional_line(configured: bool, label: str, note: str) -> str:
        return f"`{'OK' if configured else 'OPTIONAL'}` **{label}**\n{note}"

    def env_ok(self, name: str) -> bool:
        value = os.getenv(name, "").strip()
        return bool(value and not value.startswith("put-your") and value != "your-webhook-url-here")

    async def build_report(self, guild: discord.Guild, channel: discord.abc.GuildChannel | None) -> discord.Embed:
        color, theme = await self.theme(guild.id)
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        me = guild.me or guild.get_member(self.bot.user.id)
        guild_perms = me.guild_permissions if me else discord.Permissions.none()
        channel_perms = channel.permissions_for(me) if channel and me else discord.Permissions.none()

        prefix = settings.get("prefix", self.bot.settings.default_prefix)
        ffmpeg_path = os.getenv("FFMPEG_PATH", "").strip() or shutil.which("ffmpeg")
        opus_path = os.getenv("OPUS_PATH", "").strip()
        cookies_configured = self.env_ok("YTDLP_COOKIES_TEXT") or self.env_ok("YTDLP_COOKIES_FILE")
        spotify_id = self.env_ok("SPOTIFY_CLIENT_ID")
        spotify_secret = self.env_ok("SPOTIFY_CLIENT_SECRET")
        owner_ids = getattr(self.bot.settings, "owner_ids", set())
        tree_count = len(self.bot.tree.get_commands())

        e = embed("Bot Doctor", "Quick health check for common setup problems.", color)
        e.add_field(
            name="Core",
            value="\n".join(
                [
                    self.line(bool(self.bot.user), "Bot logged in"),
                    self.line(bool(owner_ids), "OWNER_IDS set", "Add your Discord user ID to Railway `OWNER_IDS`."),
                    self.line(bool(getattr(self.bot.intents, "message_content", False)), "Message Content Intent enabled in code", "Turn on Message Content Intent in the Discord Developer Portal too."),
                    self.line(bool(prefix), f"Prefix loaded: `{prefix}`"),
                    self.line(tree_count > 0, f"Slash commands loaded: `{tree_count}`", "Run `/sync` after redeploy."),
                ]
            )[:1024],
            inline=False,
        )
        e.add_field(
            name="Server Permissions",
            value="\n".join(
                [
                    self.line(guild_perms.administrator or guild_perms.manage_roles, "Manage Roles", "Move the bot role high and give Manage Roles."),
                    self.line(guild_perms.administrator or guild_perms.manage_channels, "Manage Channels", "Needed for JTC, lock, hide, category tools."),
                    self.line(guild_perms.administrator or guild_perms.view_audit_log, "View Audit Log", "Needed for anti-nuke detection."),
                    self.line(guild_perms.administrator or guild_perms.ban_members, "Ban Members", "Needed for moderation and anti-nuke punishments."),
                    self.line(guild_perms.administrator or guild_perms.moderate_members, "Timeout Members", "Needed for timeout commands."),
                    self.line(guild_perms.administrator or guild_perms.move_members, "Move Members", "Needed for VC drag/move tools."),
                ]
            )[:1024],
            inline=False,
        )
        e.add_field(
            name="This Channel",
            value="\n".join(
                [
                    self.line(channel_perms.send_messages, "Send Messages", "Let the bot send messages in this channel/category."),
                    self.line(channel_perms.embed_links, "Embed Links", "Needed for panels and clean responses."),
                    self.line(channel_perms.manage_messages, "Manage Messages", "Needed for pinned/refreshing panels."),
                    self.line(channel_perms.view_channel, "View Channel", "Needed so the bot can see this channel."),
                ]
            )[:1024],
            inline=False,
        )
        e.add_field(
            name="Music",
            value="\n".join(
                [
                    self.line(bool(getattr(self.bot.settings, "enable_music", True)), "Music enabled", "Set `ENABLE_MUSIC=true`."),
                    self.line(bool(ffmpeg_path), f"FFmpeg ready{f': `{ffmpeg_path}`' if ffmpeg_path else ''}", "Install `ffmpeg` through `nixpacks.toml`, or set `FFMPEG_PATH`."),
                    self.line(discord.opus.is_loaded() or bool(opus_path), "Opus ready", "Install `libopus`, or set `OPUS_PATH`."),
                    self.optional_line(cookies_configured, "YouTube cookies", "Configured." if cookies_configured else "Not set. Only needed if YouTube blocks playback."),
                    (self.line(False, "Spotify credentials incomplete", "Set both Spotify values, or leave both blank.") if spotify_id != spotify_secret else self.optional_line(spotify_id and spotify_secret, "Spotify search", "Configured." if spotify_id and spotify_secret else "Not set. Regular music playback still works.")),
                ]
            )[:1024],
            inline=False,
        )
        e.add_field(
            name="Optional APIs",
            value="\n".join(
                [
                    self.line(self.env_ok("OPENAI_API_KEY"), "OpenAI key", "Needed for AI commands."),
                    self.line(self.env_ok("OPENWEATHER_API_KEY"), "OpenWeather key", "Needed for weather tools."),
                    self.line(self.env_ok("DEEPL_API_KEY"), "DeepL key", "Needed for translation tools."),
                    self.line(self.env_ok("BACKUP_WEBHOOK_URL"), "Backup webhook", "Needed for backup code webhook sending."),
                ]
            )[:1024],
            inline=False,
        )
        style_embed(e, banner_url=theme.get("banner_url"), flashy=theme.get("effects", False))
        return e

    @app_commands.command(name="doctor", description="Check bot setup, permissions, music, prefix, and variables")
    @app_admin()
    async def slash_doctor(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        report = await self.build_report(interaction.guild, interaction.channel)
        await interaction.followup.send(embed=report, ephemeral=True)

    @commands.command(name="doctor")
    @has_guild_permissions(manage_guild=True)
    async def prefix_doctor(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            return
        report = await self.build_report(ctx.guild, ctx.channel)
        await ctx.reply(embed=report, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Doctor(bot))
