"""Async SQLAlchemy engine/session management for the application."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from orchestrator.core.config import get_settings
from orchestrator.models.base import Base

settings = get_settings()
engine = create_async_engine(settings.DATABASE_URL)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for FastAPI dependencies."""
    async with async_session_factory() as session:
        yield session


async def create_tables() -> None:
    """Create all ORM tables registered in SQLAlchemy metadata."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
