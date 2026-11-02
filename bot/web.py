import logging

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.config import Settings

logger = logging.getLogger(__name__)
ENGINE_KEY = web.AppKey("engine", AsyncEngine)


async def health(request: web.Request) -> web.Response:
    try:
        async with request.app[ENGINE_KEY].connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001
        logger.warning("Healthcheck: БД недоступна: %s", type(error).__name__)
        return web.json_response({"status": "db_unavailable"}, status=503)
    return web.json_response({"status": "ok"})


async def start_web(
    settings: Settings, engine: AsyncEngine, bot: Bot | None = None, dp: Dispatcher | None = None
) -> web.AppRunner:
    """Поднимает HTTP-сервер: /health всегда, /webhook — если переданы bot и dp."""
    app = web.Application()
    app[ENGINE_KEY] = engine
    app.router.add_get("/health", health)
    if bot is not None and dp is not None:
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret_value).register(
            app, path=settings.webhook_path
        )
        setup_application(app, dp, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=settings.port).start()
    logger.info("HTTP-сервер запущен на порту %s", settings.port)
    return runner
