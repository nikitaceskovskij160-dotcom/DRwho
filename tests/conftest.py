from collections.abc import AsyncIterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, Doctor
from bot.security.crypto import init_crypto
from bot.services.registration import register_doctor


@pytest.fixture(autouse=True, scope="session")
def crypto() -> None:
    init_crypto(Fernet.generate_key().decode())


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _doctor(session: AsyncSession, telegram_id: int, name: str, tz: str = "Europe/Berlin") -> Doctor:
    doctor = await register_doctor(session, telegram_id, name, "Терапевт", tz)
    assert doctor is not None
    return doctor


@pytest.fixture
async def doctor(session: AsyncSession) -> Doctor:
    return await _doctor(session, 1001, "Тестов Тест Тестович")


@pytest.fixture
async def other_doctor(session: AsyncSession) -> Doctor:
    return await _doctor(session, 1002, "Другой Врач Врачевич")
