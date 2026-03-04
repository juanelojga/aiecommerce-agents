"""FastAPI application entry point.

Creates and configures the ASGI application, middleware, and routers.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.api.routes.health import router as health_router
from orchestrator.core.config import get_settings
from orchestrator.core.database import create_tables
from orchestrator.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Run application startup and shutdown lifecycle tasks."""
    await create_tables()
    yield


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application.

    Returns:
        A fully configured FastAPI instance.
    """
    settings = get_settings()
    setup_logging(debug=settings.DEBUG)

    application = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ─────────────────────────────────────────────────────────
    application.include_router(health_router)

    logger.info("Application started — %s", settings.APP_NAME)
    return application


app = create_app()
