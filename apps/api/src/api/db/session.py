"""Async SQLAlchemy engine and sessionmaker."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield a session, commit on success, rollback on error, close at the end."""
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
