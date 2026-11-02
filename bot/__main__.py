import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import Settings, get_settings
from bot.db.session import create_engine, create_session_factory
from bot.handlers import setup_routers
from bot.middlewares import AuthMiddleware, DbSessionMiddleware
from bot.scheduler import create_scheduler
from bot.security.crypto import init_crypto
from bot.web import start_web

logger = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="menu", description="Главное меню"),
    BotCommand(command="patients", description="Список пациентов"),
    BotCommand(command="add", description="Добавить пациента"),
    BotCommand(command="search", description="Найти пациента"),
    BotCommand(command="today", description="Напоминания на сегодня"),
    BotCommand(command="reminders", description="Все напоминания"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="cancel", description="Отменить действие"),
]


def build_storage(settings: Settings) -> BaseStorage:
    if not settings.redis_url:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

    return RedisStorage.from_url(
        settings.redis_url,
        key_builder=DefaultKeyBuilder(prefix="drwho"),
        state_ttl=86400,
        data_ttl=86400,
    )


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    init_crypto(settings.encryption_key)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=build_storage(settings), settings=settings)
    dp.update.outer_middleware(DbSessionMiddleware(session_factory))
    dp.update.outer_middleware(AuthMiddleware())
    dp.include_router(setup_routers())

    await bot.set_my_commands(COMMANDS)
    scheduler = create_scheduler(bot, session_factory)
    scheduler.start()

    webhook_url = settings.webhook_url
    runner = await start_web(settings, engine, bot, dp) if webhook_url else await start_web(settings, engine)
    try:
        if webhook_url:
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.webhook_secret_value,
                allowed_updates=dp.resolve_used_update_types(),
            )
            logger.info("Режим webhook")
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook()
            logger.info("Режим polling")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await runner.cleanup()
        await engine.dispose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
