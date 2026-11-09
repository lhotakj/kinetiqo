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
    display_name: str = "Base Provider"
    description: str = ""
    default_model: str = "default"
    deprecated_models: frozenset[str] = frozenset()
    preferred_models: tuple[str, ...] = ()

    # Declarative Manifest & Setup Metadata
    auth_type: str = "api_key"  # "api_key" or "url_and_key"
    api_key_placeholder: str = "Enter API key"
    model_mode: str = "curated"  # "discovered" (auto-populated via list_models) or "curated" (user-added)
    suggested_models: tuple[dict[str, str], ...] = ()
    docs_url: str = ""
    validate_on_refresh: bool = False

    @classmethod
    def get_manifest(cls) -> dict[str, Any]:
        """Return declarative manifest metadata for UI settings and API discovery."""
        return {
            "id": cls.provider_name,
            "provider": cls.provider_name,
            "display_name": cls.display_name,
            "description": cls.description,
            "auth_type": cls.auth_type,
            "api_key_placeholder": cls.api_key_placeholder,
            "model_mode": cls.model_mode,
            "default_model": cls.default_model,
            "suggested_models": list(cls.suggested_models),
            "docs_url": cls.docs_url,
            "validate_on_refresh": cls.validate_on_refresh,
        }

    def __init__(self, api_key: str, client_factory: Any = None):
        self.api_key = api_key
        self.client_factory = client_factory

    @abstractmethod
    def list_models(self) -> list[ChatProviderModel]:
        """Return discovered, operational chat completion models for this provider."""
        raise NotImplementedError

    def validate_credentials(self) -> None:
        """Validate credentials against upstream provider.

        Default implementation calls list_models() for auto-discovered providers.
        Curated providers override this to check upstream auth endpoints.
        Raises ChatAuthenticationError when rejected.
        """
        if self.model_mode == "discovered":
            self.list_models()

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate or normalize a model identifier. Override in providers supporting model validation."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID is required.")
        return {
            "id": clean_id,
            "name": clean_id,
            "display_name": clean_id,
            "supports_tools": True,
            "supports_vision": False,
        }

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

