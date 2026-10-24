"""Explicit chat-provider registry supporting multiple AI backends."""

from kinetiqo.chat.providers.base import BaseChatProvider
from kinetiqo.chat.providers.gemini import GeminiChatProvider

PROVIDER_REGISTRY: dict[str, type[BaseChatProvider]] = {
    "gemini": GeminiChatProvider,
}


def register_provider(name: str, provider_cls: type[BaseChatProvider]) -> None:
    """Register an AI provider implementation (OpenAI, Mistral, Anthropic, etc.)."""
    PROVIDER_REGISTRY[name.lower()] = provider_cls


__all__ = ["BaseChatProvider", "GeminiChatProvider", "PROVIDER_REGISTRY", "register_provider"]

