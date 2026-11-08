"""Explicit chat-provider registry supporting multiple AI backends."""

from typing import Any

from kinetiqo.chat.providers.base import BaseChatProvider
from kinetiqo.chat.providers.gemini import GeminiChatProvider
from kinetiqo.chat.providers.kilo import KiloChatProvider
from kinetiqo.chat.providers.mistral import MistralChatProvider
from kinetiqo.chat.providers.ollama import OllamaChatProvider
from kinetiqo.chat.providers.openrouter import OpenRouterChatProvider
from kinetiqo.chat.providers.poe import PoeChatProvider
from kinetiqo.chat.providers.vercel import VercelChatProvider

PROVIDER_REGISTRY: dict[str, type[BaseChatProvider]] = {
    "gemini": GeminiChatProvider,
    "openrouter": OpenRouterChatProvider,
    "vercel": VercelChatProvider,
    "kilo": KiloChatProvider,
    "poe": PoeChatProvider,
    "ollama": OllamaChatProvider,
    "mistral": MistralChatProvider,
}


def register_provider(name: str, provider_cls: type[BaseChatProvider]) -> None:
    """Register an AI provider implementation (OpenAI, Mistral, Anthropic, OpenRouter, Vercel, etc.)."""
    PROVIDER_REGISTRY[name.lower()] = provider_cls


def get_provider_class(name: str) -> type[BaseChatProvider] | None:
    """Return provider implementation class by name if registered."""
    return PROVIDER_REGISTRY.get((name or "").strip().lower())


def get_provider_manifest(name: str) -> dict[str, Any] | None:
    """Return provider declarative manifest metadata by name if registered."""
    cls = get_provider_class(name)
    return cls.get_manifest() if cls else None


def list_all_provider_manifests() -> list[dict[str, Any]]:
    """Return list of all registered provider manifests."""
    return [cls.get_manifest() for cls in PROVIDER_REGISTRY.values()]


__all__ = [
    "BaseChatProvider",
    "GeminiChatProvider",
    "KiloChatProvider",
    "MistralChatProvider",
    "OllamaChatProvider",
    "PoeChatProvider",
    "OpenRouterChatProvider",
    "VercelChatProvider",
    "PROVIDER_REGISTRY",
    "register_provider",
    "get_provider_class",
    "get_provider_manifest",
    "list_all_provider_manifests",
]
