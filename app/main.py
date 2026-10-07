import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from app.config import settings
from app.db import engine
from app.models import Base
from app.schema import ensure_schema
from app.middlewares import SubscriptionMiddleware
from app.handlers.common import router as common_router
from app.handlers.profile import router as profile_router
from app.handlers.tournaments import router as tournaments_router
from app.handlers.gold import router as gold_router
from app.handlers.stats import router as stats_router
from app.handlers.withdrawals import router as withdrawals_router
from app.handlers.promo import router as promo_router
from app.handlers.admin import router as admin_router


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("bot")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema()
    log.info("Database ready")

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    # admin раньше — FSM админки не перехватывается
    dp.include_router(admin_router)
    dp.include_router(common_router)
    dp.include_router(profile_router)
    dp.include_router(tournaments_router)
    dp.include_router(gold_router)
    dp.include_router(stats_router)
    dp.include_router(withdrawals_router)
    dp.include_router(promo_router)

    me = await bot.get_me()
    log.info("Starting bot @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
