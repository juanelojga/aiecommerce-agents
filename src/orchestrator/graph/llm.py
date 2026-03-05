"""LLM provider abstraction for LangGraph nodes.

Defines a provider-agnostic interface so the underlying LLM can be swapped
without modifying any graph node logic.

Usage::

    from orchestrator.graph.llm import get_llm

    llm = get_llm()  # returns a configured BaseChatModel
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from orchestrator.core.config import Settings, get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


class LLMProvider(ABC):
    """Abstract base class for LLM provider implementations.

    Implement this interface to support different LLM backends
    (OpenRouter, direct OpenAI, Anthropic, etc.) without changing
    any downstream graph node code.
    """

    @abstractmethod
    def get_model(self) -> BaseChatModel:
        """Return a configured, ready-to-use chat model instance.

        Returns:
            A ``BaseChatModel`` compatible with LangChain / LangGraph.
        """
        ...


class OpenRouterProvider(LLMProvider):
    """LLM provider backed by OpenRouter.

    Uses ``langchain-openai`` with a custom ``base_url`` pointed at the
    OpenRouter API, which exposes an OpenAI-compatible interface.

    Args:
        settings: Application settings instance. Defaults to the cached
            singleton returned by ``get_settings()``.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def get_model(self) -> BaseChatModel:
        """Return a ``ChatOpenAI`` instance configured for OpenRouter.

        Returns:
            A ``ChatOpenAI`` model pointed at ``https://openrouter.ai/api/v1``.
        """
        return ChatOpenAI(
            api_key=SecretStr(self._settings.OPENROUTER_API_KEY),
            base_url=self._settings.OPENROUTER_BASE_URL,
            model=self._settings.OPENROUTER_MODEL,
        )


def get_llm(provider: LLMProvider | None = None) -> BaseChatModel:
    """Return a configured chat model using the given provider.

    Defaults to ``OpenRouterProvider`` if no provider is supplied.

    Args:
        provider: Optional ``LLMProvider`` instance. When ``None``,
            ``OpenRouterProvider`` is used with the default settings.

    Returns:
        A ``BaseChatModel`` ready for use in LangGraph nodes.

    Example::

        llm = get_llm()
        response = await llm.ainvoke("List three PC tiers.")
    """
    if provider is None:
        provider = OpenRouterProvider()
    return provider.get_model()
