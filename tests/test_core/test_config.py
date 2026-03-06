"""Tests for Gemini API configuration settings in ``Settings``."""

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
