"""Shared fixtures for model tests."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import all models so Base.metadata discovers them before create_all.
import orchestrator.models  # noqa: F401
from orchestrator.models.base import Base


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine]:
    """Yield an in-memory SQLite async engine with all ORM tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(sqlite_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Yield an async DB session bound to the in-memory SQLite engine."""
    factory = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
