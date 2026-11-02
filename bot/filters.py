from aiogram.filters import Filter
from aiogram.types import TelegramObject, User

from bot.config import Settings
from bot.db.models import Doctor


class IsDoctor(Filter):
    async def __call__(self, event: TelegramObject, doctor: Doctor | None = None) -> bool:
        return doctor is not None


class IsAdmin(Filter):
    async def __call__(
        self, event: TelegramObject, settings: Settings, event_from_user: User | None = None
    ) -> bool:
        return event_from_user is not None and event_from_user.id in settings.admin_id_set
