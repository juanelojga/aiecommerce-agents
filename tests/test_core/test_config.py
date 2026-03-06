"""Tests for application configuration settings in ``Settings``."""

import pytest

from orchestrator.core.config import Settings


class TestGeminiDefaults:
    """Tests verifying default values for Gemini settings."""

    @pytest.fixture()
    def settings(self) -> Settings:
        """Return a ``Settings`` instance with only the required DB URL overridden."""
        return Settings(DATABASE_URL="sqlite+aiosqlite:///./test.db")

    def test_settings_gemini_defaults(self, settings: Settings) -> None:
        """Default values for all Gemini settings are correct."""
        assert settings.GOOGLE_API_KEY == ""
        assert settings.GEMINI_IMAGE_MODEL == "imagen-3.0-generate-002"
        assert settings.GEMINI_VIDEO_MODEL == "veo-2.0-generate-001"
        assert settings.MEDIA_IMAGES_PER_LISTING == 4
        assert settings.MEDIA_VIDEOS_PER_LISTING == 1
        assert settings.MEDIA_GENERATION_TIMEOUT == 600


class TestGeminiFromEnv:
    """Tests verifying that Gemini settings load from environment variables."""

    def test_settings_gemini_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings load from environment variables."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-api-key")
        monkeypatch.setenv("GEMINI_IMAGE_MODEL", "imagen-custom-model")
        monkeypatch.setenv("GEMINI_VIDEO_MODEL", "veo-custom-model")
        monkeypatch.setenv("MEDIA_IMAGES_PER_LISTING", "8")
        monkeypatch.setenv("MEDIA_VIDEOS_PER_LISTING", "2")
        monkeypatch.setenv("MEDIA_GENERATION_TIMEOUT", "300")

        settings = Settings(DATABASE_URL="sqlite+aiosqlite:///./test.db")

        assert settings.GOOGLE_API_KEY == "test-google-api-key"
        assert settings.GEMINI_IMAGE_MODEL == "imagen-custom-model"
        assert settings.GEMINI_VIDEO_MODEL == "veo-custom-model"
        assert settings.MEDIA_IMAGES_PER_LISTING == 8
        assert settings.MEDIA_VIDEOS_PER_LISTING == 2
        assert settings.MEDIA_GENERATION_TIMEOUT == 300


class TestGeminiEmptyApiKey:
    """Tests verifying that an empty API key is allowed."""

    def test_settings_gemini_empty_api_key(self) -> None:
        """Empty API key is allowed (for testing/CI)."""
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///./test.db",
            GOOGLE_API_KEY="",
        )
        assert settings.GOOGLE_API_KEY == ""


class TestPublicationConfigDefaults:
    """Tests verifying default values for publication configuration settings."""

    @pytest.fixture()
    def settings(self) -> Settings:
        """Return a ``Settings`` instance with only the required DB URL overridden."""
        return Settings(DATABASE_URL="sqlite+aiosqlite:///./test.db")

    def test_settings_default_ml_api_url(self, settings: Settings) -> None:
        """Default ML API URL is ``https://api.mercadolibre.com``."""
        assert settings.MERCADOLIBRE_API_URL == "https://api.mercadolibre.com"

    def test_settings_default_ml_tokens(self, settings: Settings) -> None:
        """Default ML access and refresh tokens are empty strings."""
        assert settings.MERCADOLIBRE_ACCESS_TOKEN == ""
        assert settings.MERCADOLIBRE_REFRESH_TOKEN == ""

    def test_settings_default_assembly_margin(self, settings: Settings) -> None:
        """Default assembly margin percentage is 15.0."""
        assert settings.ASSEMBLY_MARGIN_PERCENT == 15.0

    def test_settings_default_ml_fee(self, settings: Settings) -> None:
        """Default ML fee percentage is 12.0."""
        assert settings.ML_FEE_PERCENT == 12.0


class TestPublicationConfigFromEnv:
    """Tests verifying that publication configuration settings load from env vars."""

    def test_settings_custom_pricing_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Margin and fee percentages can be overridden via environment variables."""
        monkeypatch.setenv("ASSEMBLY_MARGIN_PERCENT", "20.0")
        monkeypatch.setenv("ML_FEE_PERCENT", "10.5")

        settings = Settings(DATABASE_URL="sqlite+aiosqlite:///./test.db")

        assert settings.ASSEMBLY_MARGIN_PERCENT == 20.0
        assert settings.ML_FEE_PERCENT == 10.5
