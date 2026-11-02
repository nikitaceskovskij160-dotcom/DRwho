from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import DateTime, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from bot.security.crypto import get_crypto


class EncryptedString(TypeDecorator[str]):
    """Строка, которая хранится в БД в зашифрованном виде (Fernet)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        return None if value is None else get_crypto().encrypt(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        return None if value is None else get_crypto().decrypt(value)


class EncryptedDate(TypeDecorator[date]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: date | None, dialect: Dialect) -> str | None:
        return None if value is None else get_crypto().encrypt(value.isoformat())

    def process_result_value(self, value: Any, dialect: Dialect) -> date | None:
        return None if value is None else date.fromisoformat(get_crypto().decrypt(value))


class UTCDateTime(TypeDecorator[datetime]):
    """Хранит время в UTC и всегда возвращает aware-datetime (в т.ч. на SQLite)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Ожидается datetime с часовым поясом")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
