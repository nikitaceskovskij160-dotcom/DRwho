from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.services.registration import get_doctor

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Одна сессия БД на апдейт: коммит при успехе, откат при исключении."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result


class AuthMiddleware(BaseMiddleware):
    """Кладёт в data["doctor"] зарегистрированного активного врача или None."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("event_from_user")
        doctor = None
        if user is not None:
            doctor = await get_doctor(data["session"], user.id)
            if doctor is not None and not doctor.is_active:
                doctor = None
        data["doctor"] = doctor
        return await handler(event, data)
