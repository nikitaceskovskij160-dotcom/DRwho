from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def normalize_db_url(url: str) -> str:
    """Приводит строку Supabase/Railway (postgres://, postgresql://) к драйверу asyncpg."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


def engine_kwargs(url: str, pooled: bool = True) -> dict[str, Any]:
    if not url.startswith("postgresql+asyncpg"):
        return {}
    connect_args: dict[str, Any] = {}
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    # asyncpg не понимает sslmode из libpq-строки
    if query.pop("sslmode", None) in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require"
    # Transaction pooler Supabase (порт 6543) не поддерживает prepared statements
    if parts.port == 6543:
        connect_args["statement_cache_size"] = 0
    kwargs: dict[str, Any] = {
        "url": urlunsplit(parts._replace(query=urlencode(query))),
        "connect_args": connect_args,
    }
    if pooled:
        kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5)
    return kwargs


def create_engine(url: str) -> AsyncEngine:
    url = normalize_db_url(url)
    kwargs = engine_kwargs(url)
    url = kwargs.pop("url", url)
    return create_async_engine(url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
