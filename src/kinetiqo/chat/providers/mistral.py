"""Mistral AI REST adapter using httpx and OpenAI-compatible streaming SSE."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
    ChatTimeoutError,
)
from kinetiqo.chat.models import ChatProviderModel, StreamEvent
from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://api.mistral.ai/v1"
logger = logging.getLogger("kinetiqo.chat.mistral")

DEPRECATED_MODELS = frozenset({
    "mistral-tiny",
    "mistral-small",
    "mistral-medium",
})

PREFERRED_MODELS = (
    "mistral-small-latest",
    "mistral-large-latest",
    "codestral-latest",
    "ministral-8b-latest",
    "ministral-3b-latest",
    "pixtral-large-latest",
    "pixtral-12b-2409",
    "open-mistral-nemo",
    "open-mistral-7b",
    "open-mixtral-8x7b",
    "open-mixtral-8x22b",
)

DEFAULT_MISTRAL_MODELS = (
    {
        "id": "mistral-small-latest",
        "name": "Mistral Small",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "description": "Cost-efficient, fast reasoning and general-purpose model",
    },
    {
        "id": "mistral-large-latest",
        "name": "Mistral Large",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "description": "Top-tier flagship reasoning model for complex tasks and analysis",
    },
    {
        "id": "codestral-latest",
        "name": "Codestral",
        "context_length": 256000,
        "supports_tools": True,
        "supports_vision": False,
        "description": "Specialized coding and structured reasoning model",
    },
    {
        "id": "ministral-8b-latest",
        "name": "Ministral 8B",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "description": "Edge-optimized and low-latency model",
    },
    {
        "id": "pixtral-large-latest",
        "name": "Pixtral Large",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Frontier multimodal vision and language model",
    },
)


class MistralChatProvider(OpenAICompatibleChatProvider):
    provider_name = "mistral"
    display_name = "Mistral AI"
    description = "Official Mistral AI API with frontier European models"
    base_url = _BASE_URL
    default_model = "mistral-small-latest"
    deprecated_models = DEPRECATED_MODELS
    preferred_models = PREFERRED_MODELS
    fallback_models = DEFAULT_MISTRAL_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter Mistral API key"
    model_mode = "discovered"
    suggested_models = ()
    docs_url = "https://docs.mistral.ai/"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["Accept"] = "application/json"
        return headers

    def _parse_model_item(self, item: dict[str, Any]) -> dict[str, Any]:
        mid = str(item.get("id") or "").strip()
        name = str(item.get("name") or mid).strip()
        capabilities = item.get("capabilities") or {}

        lower_id = mid.lower()
        is_embedding = "embed" in lower_id
        is_moderation = "moderation" in lower_id
        is_ocr = "ocr" in lower_id

        completion_chat = capabilities.get("completion_chat")
        if completion_chat is False:
            is_chat = False
        elif is_embedding or is_moderation or is_ocr:
            is_chat = False
        else:
            is_chat = True

        supports_tools = bool(capabilities.get("function_calling", True)) and not is_embedding and not is_moderation
        supports_vision = bool(capabilities.get("vision", False))
        context_len = item.get("max_context_length")

        return {
            "id": mid,
            "name": name,
            "display_name": name,
            "context_length": context_len,
            "supports_tools": supports_tools,
            "supports_vision": supports_vision,
            "description": item.get("description") or "",
            "is_chat": is_chat,
            "is_embedding": is_embedding,
            "pricing": item.get("pricing"),
            "max_output_tokens": item.get("max_tokens") or item.get("max_output_tokens"),
            "rate_limits": item.get("rate_limits"),
            "request_limits": item.get("request_limits"),
        }

    def list_models(self) -> list[ChatProviderModel]:
        """Discover models directly from Mistral AI /v1/models endpoint."""
        url = f"{self.base_url}/models"
        with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            resp = client.get(url, headers=self._headers())
            self._raise_for_status(resp)
            payload = resp.json()
            data_val = payload.get("data")
            if isinstance(data_val, list):
                raw_models = data_val
            elif isinstance(data_val, dict):
                raw_models = [data_val]
            elif isinstance(payload, list):
                raw_models = payload
            else:
                raw_models = []

            result: list[ChatProviderModel] = []
            for item in raw_models:
                parsed = self._parse_model_item(item)
                if not parsed["is_chat"] or parsed["is_embedding"]:
                    continue
                mid = parsed["id"]
                if mid.lower() in self.deprecated_models:
                    continue
                result.append(
                    ChatProviderModel(
                        id=mid,
                        display_name=parsed["display_name"],
                        supports_tools=parsed["supports_tools"],
                        supports_vision=parsed["supports_vision"],
                        context_length=parsed["context_length"],
                        max_output_tokens=parsed["max_output_tokens"],
                        pricing=parsed["pricing"],
                        rate_limits=parsed["rate_limits"],
                        request_limits=parsed["request_limits"],
                        description=parsed["description"],
                    )
                )

            def model_rank(m: ChatProviderModel) -> int:
                for idx, pref in enumerate(self.preferred_models):
                    if m.id == pref:
                        return idx
                return len(self.preferred_models) + 1

            result.sort(key=lambda m: (model_rank(m), m.id))
            logger.info("Mistral model discovery completed: available_models=%d", len(result))
            return result

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate a Mistral AI model ID by querying the models catalog."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        clean_lower = clean_id.lower()
        if "embed" in clean_lower:
            raise ValueError(
                f"'{clean_id}' is an embedding model and cannot be used for text chat. "
                "Please choose a generative chat model (such as mistral-small-latest or mistral-large-latest)."
            )

        with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            cat_url = f"{self.base_url}/models"
            resp = client.get(cat_url, headers=self._headers())
            self._raise_for_status(resp)
            payload = resp.json()
            data_val = payload.get("data")
            if isinstance(data_val, list):
                models = data_val
            elif isinstance(data_val, dict):
                models = [data_val]
            elif isinstance(payload, list):
                models = payload
            else:
                models = []

            for item in models:
                mid = (item.get("id") or "").lower()
                if mid == clean_lower:
                    parsed = self._parse_model_item(item)
                    if not parsed["is_chat"] or parsed["is_embedding"]:
                        raise ValueError(
                            f"'{clean_id}' is not a generative chat model. Please choose a chat completion model."
                        )
                    return parsed

            raise LookupError(f"Model '{clean_id}' not found in Mistral AI catalog.")


