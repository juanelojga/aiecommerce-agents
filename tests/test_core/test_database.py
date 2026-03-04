"""Tests for async database session management helpers."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import String
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

import orchestrator.main as main_module
from orchestrator.core import database
from orchestrator.models.base import Base


class DatabaseTestModel(Base):
    """SQLAlchemy model used to verify schema creation in tests."""

    __tablename__ = "_database_test_model"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Yield an in-memory SQLite async engine for database tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_db_session_yields_session(
    sqlite_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Dependency yields an AsyncSession and closes it when finished."""
    session_factory = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    close_spy = mocker.spy(session, "close")

    monkeypatch.setattr(database, "async_session_factory", lambda: session)

    session_generator = database.get_db_session()
    yielded_session = await anext(session_generator)

    assert isinstance(yielded_session, AsyncSession)
    await session_generator.aclose()
    assert close_spy.call_count == 1


@pytest.mark.asyncio
async def test_create_tables_creates_schema(
    sqlite_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_tables creates ORM metadata tables in the configured engine."""
    monkeypatch.setattr(database, "engine", sqlite_engine)

    await database.create_tables()

    async with sqlite_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = '_database_test_model'"
            )
        )
        assert result.scalar_one_or_none() == "_database_test_model"


@pytest.mark.asyncio
async def test_app_lifespan_runs_table_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Application lifespan awaits table creation on startup."""
    create_tables_mock = AsyncMock()
    monkeypatch.setattr(main_module, "create_tables", create_tables_mock)
    app = main_module.create_app()

    async with app.router.lifespan_context(app):
        pass

    create_tables_mock.assert_awaited_once()
