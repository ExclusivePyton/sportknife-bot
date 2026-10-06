import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import settings
from app.db import engine
from app.models import Base
from app.handlers.common import router as common_router
from app.handlers.profile import router as profile_router
from app.handlers.tournaments import router as tournaments_router
from app.handlers.gold import router as gold_router
from app.handlers.stats import router as stats_router
from app.handlers.withdrawals import router as withdrawals_router
from app.handlers.promo import router as promo_router
from app.handlers.admin import router as admin_router


async def main():
    logging.basicConfig(level=logging.INFO)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(profile_router)
    dp.include_router(tournaments_router)
    dp.include_router(gold_router)
    dp.include_router(stats_router)
    dp.include_router(withdrawals_router)
    dp.include_router(promo_router)
    dp.include_router(admin_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
