"""Tests for the LLM provider abstraction (graph/llm.py).

Covers:
- ``OpenRouterProvider.get_model()`` returns a ``ChatOpenAI`` instance.
- ``OpenRouterProvider`` correctly passes ``api_key``, ``base_url``, and ``model``.
- ``get_llm()`` returns a model using ``OpenRouterProvider`` by default.
- ``get_llm()`` accepts a custom provider and delegates to it.
- A custom ``LLMProvider`` subclass can be used as a substitute.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from orchestrator.core.config import Settings
from orchestrator.graph.llm import LLMProvider, OpenRouterProvider, get_llm

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def openrouter_settings() -> Settings:
    """Return a ``Settings`` instance with OpenRouter values pre-filled."""
    return Settings(
        OPENROUTER_API_KEY="sk-or-test-key",
        OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        OPENROUTER_MODEL="openai/gpt-4o-mini",
        DATABASE_URL="sqlite+aiosqlite:///./test.db",
    )


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class TestOpenRouterProvider:
    """Unit tests for ``OpenRouterProvider``."""

    def test_get_model_returns_chat_openai(self, openrouter_settings: Settings) -> None:
        """``get_model()`` must return a ``BaseChatModel`` instance."""
        provider = OpenRouterProvider(settings=openrouter_settings)
        model = provider.get_model()
        assert isinstance(model, BaseChatModel)

    def test_get_model_uses_correct_api_key(self, openrouter_settings: Settings) -> None:
        """``get_model()`` must configure the model with the correct API key."""
        provider = OpenRouterProvider(settings=openrouter_settings)
        model = provider.get_model()
        assert isinstance(model, ChatOpenAI)
        # ChatOpenAI stores the key inside ``openai_api_key`` (SecretStr)
        assert isinstance(model.openai_api_key, SecretStr)
        assert model.openai_api_key.get_secret_value() == "sk-or-test-key"

    def test_get_model_uses_correct_base_url(self, openrouter_settings: Settings) -> None:
        """``get_model()`` must configure the model with the OpenRouter base URL."""
        provider = OpenRouterProvider(settings=openrouter_settings)
        model = provider.get_model()
        assert isinstance(model, ChatOpenAI)
        assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"

    def test_get_model_uses_correct_model_name(self, openrouter_settings: Settings) -> None:
        """``get_model()`` must set the model name from settings."""
        provider = OpenRouterProvider(settings=openrouter_settings)
        model = provider.get_model()
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "openai/gpt-4o-mini"

    def test_uses_get_settings_when_no_settings_provided(self) -> None:
        """``OpenRouterProvider()`` must fall back to ``get_settings()`` when no settings given."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.OPENROUTER_API_KEY = "sk-or-fallback"
        mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
        mock_settings.OPENROUTER_MODEL = "openai/gpt-4o-mini"

        with patch("orchestrator.graph.llm.get_settings", return_value=mock_settings):
            provider = OpenRouterProvider()
            provider.get_model()


# ---------------------------------------------------------------------------
# get_llm
# ---------------------------------------------------------------------------


class TestGetLlm:
    """Unit tests for the ``get_llm()`` factory function."""

    def test_returns_base_chat_model(self, openrouter_settings: Settings) -> None:
        """``get_llm()`` must return a ``BaseChatModel``."""
        provider = OpenRouterProvider(settings=openrouter_settings)
        model = get_llm(provider=provider)
        assert isinstance(model, BaseChatModel)

    def test_uses_openrouter_provider_by_default(self) -> None:
        """``get_llm()`` with no arguments must use ``OpenRouterProvider``."""
        fake_model = MagicMock(spec=BaseChatModel)
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.get_model.return_value = fake_model

        with patch("orchestrator.graph.llm.OpenRouterProvider", return_value=mock_provider):
            result = get_llm()

        mock_provider.get_model.assert_called_once()
        assert result is fake_model

    def test_accepts_custom_provider(self) -> None:
        """``get_llm(provider=...)`` must delegate to the supplied provider."""
        fake_model = MagicMock(spec=BaseChatModel)
        custom_provider = MagicMock(spec=LLMProvider)
        custom_provider.get_model.return_value = fake_model

        result = get_llm(provider=custom_provider)

        custom_provider.get_model.assert_called_once()
        assert result is fake_model


# ---------------------------------------------------------------------------
# LLMProvider abstract interface
# ---------------------------------------------------------------------------


class TestLLMProviderInterface:
    """Ensures ``LLMProvider`` is abstract and can be subclassed."""

    def test_cannot_instantiate_abstract_provider(self) -> None:
        """``LLMProvider`` must raise ``TypeError`` when instantiated directly."""
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_is_substitutable(self, openrouter_settings: Settings) -> None:
        """A concrete subclass must be usable wherever ``LLMProvider`` is expected."""

        class ConcreteProvider(LLMProvider):
            def get_model(self) -> BaseChatModel:
                return OpenRouterProvider(settings=openrouter_settings).get_model()

        provider: LLMProvider = ConcreteProvider()
        model = get_llm(provider=provider)
        assert isinstance(model, BaseChatModel)
