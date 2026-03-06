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

    # ── MercadoLibre API ────────────────────────────────────────────────
    MERCADOLIBRE_API_URL: str = "https://api.mercadolibre.com"
    MERCADOLIBRE_ACCESS_TOKEN: str = ""
    MERCADOLIBRE_REFRESH_TOKEN: str = ""

    # ── Pricing ─────────────────────────────────────────────────────────
    ASSEMBLY_MARGIN_PERCENT: float = 15.0
    ML_FEE_PERCENT: float = 12.0

    # ── OpenRouter (LangChain / LangGraph) ────────────────────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    # ── Phase 3: Creative Asset Generation (Gemini) ───────────────────
    GOOGLE_API_KEY: str = ""
    GEMINI_IMAGE_MODEL: str = "imagen-3.0-generate-002"
    GEMINI_VIDEO_MODEL: str = "veo-2.0-generate-001"
    MEDIA_IMAGES_PER_LISTING: int = 4
    MEDIA_VIDEOS_PER_LISTING: int = 1
    MEDIA_GENERATION_TIMEOUT: int = 600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance.

    Use with FastAPI ``Depends(get_settings)`` for dependency injection.
    """
    return Settings()
