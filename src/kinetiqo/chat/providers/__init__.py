"""Explicit chat-provider registry supporting multiple AI backends."""

from kinetiqo.chat.providers.base import BaseChatProvider
from kinetiqo.chat.providers.gemini import GeminiChatProvider
from kinetiqo.chat.providers.kilo import KiloChatProvider
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
}


def register_provider(name: str, provider_cls: type[BaseChatProvider]) -> None:
    """Register an AI provider implementation (OpenAI, Mistral, Anthropic, OpenRouter, Vercel, etc.)."""
    PROVIDER_REGISTRY[name.lower()] = provider_cls


__all__ = [
    "BaseChatProvider",
    "GeminiChatProvider",
    "KiloChatProvider",
    "OllamaChatProvider",
    "PoeChatProvider",
    "OpenRouterChatProvider",
    "VercelChatProvider",
    "PROVIDER_REGISTRY",
    "register_provider",
]
