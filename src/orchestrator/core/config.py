"""Application configuration loaded from environment variables.

Uses pydantic-settings to validate and type-check all configuration values.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    All values are loaded from environment variables or a ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ─────────────────────────────────────────────────────
    APP_NAME: str = "aiecommerce-agents"
    DEBUG: bool = False
    API_PORT: int = 8000
    API_KEY: str = ""

    # ── Database (Local Registry) ───────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://orchestrator:orchestrator@localhost:5432/orchestrator"

    # ── PostgreSQL (used by Docker Compose) ─────────────────────────────
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "orchestrator"
    POSTGRES_PASSWORD: str = "orchestrator"
    POSTGRES_DB: str = "orchestrator"

    # ── AIEcommerce API ─────────────────────────────────────────────────
    AIECOMMERCE_API_URL: str = "https://api.aiecommerce.example.com"
    AIECOMMERCE_API_KEY: str = ""

    # ── MercadoLibre OAuth ──────────────────────────────────────────────
    MERCADOLIBRE_CLIENT_ID: str = ""
    MERCADOLIBRE_CLIENT_SECRET: str = ""
    MERCADOLIBRE_REDIRECT_URI: str = "https://localhost:8000/auth/callback"

    # ── OpenAI (LangChain / LangGraph) ──────────────────────────────────
    OPENAI_API_KEY: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Use with FastAPI ``Depends(get_settings)`` for dependency injection.
    """
    return Settings()
