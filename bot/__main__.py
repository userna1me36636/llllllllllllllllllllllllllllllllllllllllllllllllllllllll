import asyncio

from bot.core.bot import create_bot
from bot.core.config import Settings


async def main() -> None:
    settings = Settings.from_env()
    bot = create_bot(settings)
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
