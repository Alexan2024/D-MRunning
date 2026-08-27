import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import ADMIN_IDS, BOT_TOKEN, CLUB_CHAT_ID
from bot.db import init_db
from bot.handlers import admin, admin_manage, checkin, common, rsvp, stats
from bot.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    if not CLUB_CHAT_ID:
        log.warning("CLUB_CHAT_ID не задан — анонсы публиковаться не будут")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS пуст — админка никому не доступна")

    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # админские роутеры первыми: у них свои FSM-состояния
    dp.include_router(admin.router)
    dp.include_router(admin_manage.router)
    dp.include_router(common.router)
    dp.include_router(rsvp.router)
    dp.include_router(checkin.router)
    dp.include_router(stats.router)

    scheduler = setup_scheduler(bot)
    scheduler.start()

    log.info("Бот запущен")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
