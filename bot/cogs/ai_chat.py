from __future__ import annotations

import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import configured_owner
from bot.core.utils import embed, pulse_line


SENSITIVE_SERVER_WORDS = {
    "admin",
    "antinuke",
    "automod",
    "backup",
    "ban",
    "bans",
    "channel",
    "channels",
    "config",
    "kick",
    "logs",
    "moderation",
    "owner",
    "permission",
    "permissions",
    "role",
    "roles",
    "settings",
    "timeout",
    "whitelist",
}


class AiChat(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ai_group = app_commands.Group(name="ai", description="AI chat controls")
        self.ai_group.add_command(app_commands.Command(name="toggle", description="Turn AI chat on or off", callback=self.ai_toggle))
        self.ai_group.add_command(app_commands.Command(name="speak", description="Ask the AI a question", callback=self.ai_speak))
        self.bot.tree.add_command(self.ai_group)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command("ai")

    async def ai_settings(self, guild_id: int) -> dict:
        settings = await self.bot.db.get_settings(guild_id, self.bot.settings.default_prefix)
        return settings.get("ai_chat", {"enabled": False})

    async def save_ai_settings(self, guild_id: int, data: dict) -> None:
        await self.bot.db.set_settings_value(guild_id, "ai_chat", data, self.bot.settings.default_prefix)

    async def is_admin_user(self, user: discord.abc.User, guild: discord.Guild | None) -> bool:
        if await configured_owner(self.bot, user):
            return True
        return isinstance(user, discord.Member) and guild is not None and user.guild_permissions.administrator

    def needs_admin_context(self, prompt: str) -> bool:
        words = {word.strip(".,!?;:()[]{}").lower() for word in prompt.split()}
        return bool(words & SENSITIVE_SERVER_WORDS)

    async def server_context(self, guild: discord.Guild | None, admin: bool) -> str:
        if guild is None:
            return "No server context."
        settings = await self.bot.db.get_settings(guild.id, self.bot.settings.default_prefix)
        basics = [
            f"Server name: {guild.name}",
            f"Server ID: {guild.id}",
            f"Members: {guild.member_count or 'unknown'}",
            f"Text channels: {len(guild.text_channels)}",
            f"Voice channels: {len(guild.voice_channels)}",
            f"Roles: {len(guild.roles)}",
            f"Default prefix: {settings.get('prefix', self.bot.settings.default_prefix)}",
        ]
        if not admin:
            basics.append("The user is not admin. Do not reveal role lists, channel lists, moderation settings, security config, backups, logs, or private setup details.")
            return "\n".join(basics)

        role_names = [role.name for role in guild.roles if role.name != "@everyone"][-35:]
        text_names = [channel.name for channel in guild.text_channels[:35]]
        voice_names = [channel.name for channel in guild.voice_channels[:35]]
        deeper = [
            "The user is admin or OWNER_IDS, so deeper server details are allowed.",
            f"Roles visible to the bot: {', '.join(role_names) if role_names else 'none'}",
            f"Text channels visible to the bot: {', '.join(text_names) if text_names else 'none'}",
            f"Voice channels visible to the bot: {', '.join(voice_names) if voice_names else 'none'}",
            f"Anti-nuke settings: {settings.get('antinuke', {})}",
            f"Automod settings: {settings.get('automod', {})}",
            f"JTC settings: {settings.get('jtc', {})}",
            f"Welcome settings: {settings.get('welcome', {})}",
            f"Logs settings: {settings.get('logs', {})}",
        ]
        return "\n".join(basics + deeper)

    async def ask_ai(self, prompt: str, user: discord.abc.User, guild: discord.Guild | None = None, admin: bool | None = None) -> str:
        key = self.bot.settings.openai_api_key
        if not key:
            return "AI needs `OPENAI_API_KEY` in Railway Variables."
        is_admin = await self.is_admin_user(user, guild) if admin is None else admin
        if self.needs_admin_context(prompt) and not is_admin:
            return "That is an admin-only server question. Ask someone with Admin or an OWNER_IDS user to use `/ai speak`."
        context = await self.server_context(guild, is_admin)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        system = (
            "You are AinBot, a helpful Discord server assistant. "
            "Keep answers short, friendly, and useful. "
            "Understand common abbreviations and slang like idk, tbh, ngl, rn, wtv, wyd, wym, fr, vc, pfp, jtc, mod, and perms. "
            "Do not help with token stealing, scams, or harmful actions. "
            "Use the server context when answering server questions. "
            "If the context says the user is not admin, keep server answers basic and do not reveal private server setup."
        )
        system += f"\n\nServer context:\n{context}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{user.display_name}: {prompt[:1800]}"},
            ],
            "temperature": 0.7,
            "max_tokens": 450,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=45) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    message = data.get("error", {}).get("message", "AI request failed.")
                    return f"AI error: `{message[:400]}`"
        return data["choices"][0]["message"]["content"][:1900]

    async def ai_toggle(self, interaction: discord.Interaction, enabled: bool | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        if not await self.is_admin_user(interaction.user, interaction.guild):
            await interaction.response.send_message("Administrator only.", ephemeral=True)
            return
        settings = await self.ai_settings(interaction.guild_id)
        new_state = (not settings.get("enabled", False)) if enabled is None else enabled
        settings["enabled"] = new_state
        await self.save_ai_settings(interaction.guild_id, settings)
        state = "on" if new_state else "off"
        e = embed("AI Chat", f"{pulse_line()}\n\nAI chat is now **{state}**.")
        e.add_field(name="Use", value="`ain speak your question` or mention the bot.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def ai_speak(self, interaction: discord.Interaction, question: str) -> None:
        admin = await self.is_admin_user(interaction.user, interaction.guild)
        private = admin or self.needs_admin_context(question)
        await interaction.response.defer(ephemeral=private)
        answer = await self.ask_ai(question, interaction.user, interaction.guild, admin)
        await interaction.followup.send(embed=embed("Ain AI", answer), ephemeral=private)

    @commands.group(name="ai", aliases=["aic", "a"], invoke_without_command=True)
    async def ai_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("Use `ai toggle` or `ain speak your question`.", mention_author=False)

    @ai_prefix.command(name="toggle", aliases=["tog", "onoff"])
    async def ai_prefix_toggle(self, ctx: commands.Context, enabled: str | None = None) -> None:
        if not await self.is_admin_user(ctx.author, ctx.guild):
            await ctx.reply("Administrator only.", mention_author=False)
            return
        settings = await self.ai_settings(ctx.guild.id)
        if enabled is None:
            new_state = not settings.get("enabled", False)
        else:
            new_state = enabled.lower() in {"on", "true", "yes", "enable", "enabled"}
        settings["enabled"] = new_state
        await self.save_ai_settings(ctx.guild.id, settings)
        state = "on" if new_state else "off"
        e = embed("AI Chat", f"{pulse_line()}\n\nAI chat is now **{state}**.")
        e.add_field(name="Use", value="`ain speak your question` or mention the bot.", inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @commands.group(name="ain", aliases=["ainbot"], invoke_without_command=True)
    async def ain_prefix(self, ctx: commands.Context, *, question: str | None = None) -> None:
        if not question:
            await ctx.reply("Use `ain speak your question`.", mention_author=False)
            return
        await self.answer_prefix(ctx, question)

    @ain_prefix.command(name="speak", aliases=["ask", "talk", "spk", "q", "s"])
    async def ain_speak_prefix(self, ctx: commands.Context, *, question: str) -> None:
        await self.answer_prefix(ctx, question)

    async def answer_prefix(self, ctx: commands.Context, question: str) -> None:
        admin = await self.is_admin_user(ctx.author, ctx.guild)
        if admin and self.needs_admin_context(question):
            await ctx.reply("Use `/ai speak` for admin server questions so only you can see the answer.", mention_author=False)
            return
        async with ctx.typing():
            answer = await self.ask_ai(question, ctx.author, ctx.guild, admin)
        await ctx.reply(embed=embed("Ain AI", answer), mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        content = message.content.strip()
        lower = content.lower()
        bot_mentioned = self.bot.user in message.mentions if self.bot.user else False
        direct_prefixes = ("ain speak ", "ain ask ", "ai speak ", "ai ask ")
        direct_question = None
        for prefix in direct_prefixes:
            if lower.startswith(prefix):
                direct_question = content[len(prefix):].strip()
                break
        if direct_question:
            admin = await self.is_admin_user(message.author, message.guild)
            if admin and self.needs_admin_context(direct_question):
                await message.reply("Use `/ai speak` for admin server questions so only you can see the answer.", mention_author=False)
                return
            async with message.channel.typing():
                answer = await self.ask_ai(direct_question, message.author, message.guild, admin)
            await message.reply(embed=embed("Ain AI", answer), mention_author=False)
            return

        settings = await self.ai_settings(message.guild.id)
        if not settings.get("enabled", False):
            return
        prefixes = ("ain ", "ain,", "ain:", "ai ")
        if not bot_mentioned and not lower.startswith(prefixes):
            return
        cleaned = content
        if bot_mentioned and self.bot.user:
            cleaned = cleaned.replace(self.bot.user.mention, "").strip()
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        if not cleaned:
            return
        admin = await self.is_admin_user(message.author, message.guild)
        if admin and self.needs_admin_context(cleaned):
            await message.reply("Use `/ai speak` for admin server questions so only you can see the answer.", mention_author=False)
            return
        async with message.channel.typing():
            answer = await self.ask_ai(cleaned, message.author, message.guild, admin)
        await message.reply(embed=embed("Ain AI", answer), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AiChat(bot))
