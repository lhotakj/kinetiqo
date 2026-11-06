"""Abstract base provider interface for AI Chat backends.

Enables seamless multi-provider support (Google Gemini, OpenAI, Mistral, Anthropic, etc.)
with uniform model listing, parameterization, and streaming function calling.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, Callable

from kinetiqo.chat.models import ChatProviderModel, StreamEvent


class BaseChatProvider(ABC):
    """Abstract contract that every completion backend must implement."""

    provider_name: str = "base"
    default_model: str = "default"
    deprecated_models: frozenset[str] = frozenset()
    preferred_models: tuple[str, ...] = ()

    def __init__(self, api_key: str, client_factory: Any = None):
        self.api_key = api_key
        self.client_factory = client_factory

    @abstractmethod
    def list_models(self) -> list[ChatProviderModel]:
        """Return discovered, operational chat completion models for this provider."""
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        model_id: str,
        system_instruction: str,
        history: list[dict[str, str]],
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Callable[[str, dict[str, Any]], tuple[dict[str, Any], int]] | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream completion events with optional multi-turn tool calling."""
        raise NotImplementedError

