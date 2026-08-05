from __future__ import annotations

import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot.core.checks import app_admin
from bot.core.utils import embed, pulse_line


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

    async def ask_ai(self, prompt: str, user: discord.abc.User, guild: discord.Guild | None = None) -> str:
        key = self.bot.settings.openai_api_key
        if not key:
            return "AI needs `OPENAI_API_KEY` in Railway Variables."
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        system = (
            "You are AinBot, a helpful Discord server assistant. "
            "Keep answers short, friendly, and useful. "
            "Understand common abbreviations and slang like idk, tbh, ngl, rn, wtv, wyd, wym, fr, vc, pfp, jtc, mod, and perms. "
            "Do not help with token stealing, scams, or harmful actions."
        )
        if guild:
            system += f" Server name: {guild.name}."
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
        if not interaction.user.guild_permissions.administrator:
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
        await interaction.response.defer()
        answer = await self.ask_ai(question, interaction.user, interaction.guild)
        await interaction.followup.send(embed=embed("Ain AI", answer))

    @commands.group(name="ai", aliases=["aic", "a"], invoke_without_command=True)
    async def ai_prefix(self, ctx: commands.Context) -> None:
        await ctx.reply("Use `ai toggle` or `ain speak your question`.", mention_author=False)

    @ai_prefix.command(name="toggle", aliases=["tog", "onoff"])
    @commands.has_permissions(administrator=True)
    async def ai_prefix_toggle(self, ctx: commands.Context, enabled: str | None = None) -> None:
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
        async with ctx.typing():
            answer = await self.ask_ai(question, ctx.author, ctx.guild)
        await ctx.reply(embed=embed("Ain AI", answer), mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        settings = await self.ai_settings(message.guild.id)
        if not settings.get("enabled", False):
            return
        content = message.content.strip()
        lower = content.lower()
        bot_mentioned = self.bot.user in message.mentions if self.bot.user else False
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
        async with message.channel.typing():
            answer = await self.ask_ai(cleaned, message.author, message.guild)
        await message.reply(embed=embed("Ain AI", answer), mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AiChat(bot))
