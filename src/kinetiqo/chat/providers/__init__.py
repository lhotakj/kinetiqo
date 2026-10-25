"""Explicit chat-provider registry supporting multiple AI backends."""

from kinetiqo.chat.providers.base import BaseChatProvider
from kinetiqo.chat.providers.gemini import GeminiChatProvider
from kinetiqo.chat.providers.ollama import OllamaChatProvider
from kinetiqo.chat.providers.openrouter import OpenRouterChatProvider

PROVIDER_REGISTRY: dict[str, type[BaseChatProvider]] = {
    "gemini": GeminiChatProvider,
    "openrouter": OpenRouterChatProvider,
    "ollama": OllamaChatProvider,
}


def register_provider(name: str, provider_cls: type[BaseChatProvider]) -> None:
    """Register an AI provider implementation (OpenAI, Mistral, Anthropic, OpenRouter, etc.)."""
    PROVIDER_REGISTRY[name.lower()] = provider_cls


__all__ = [
    "BaseChatProvider",
    "GeminiChatProvider",
    "OllamaChatProvider",
    "OpenRouterChatProvider",
    "PROVIDER_REGISTRY",
    "register_provider",
]

