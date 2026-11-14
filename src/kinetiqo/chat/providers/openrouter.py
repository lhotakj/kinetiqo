"""OpenRouter REST adapter using httpx and OpenAI-compatible streaming SSE."""

import logging
from typing import Any

import httpx

from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://openrouter.ai/api/v1"
logger = logging.getLogger("kinetiqo.chat.openrouter")

DEFAULT_OPENROUTER_MODELS = (
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Meta: Llama 3.3 70B Instruct",
        "context_length": 131072,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek: DeepSeek V3",
        "context_length": 64000,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "Qwen: Qwen 2.5 72B Instruct",
        "context_length": 131072,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "google/gemma-4-26b-a4b-it:free",
        "name": "Google: Gemma 4 26B A4B (Free)",
        "context_length": 262144,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "nvidia/nemotron-3.5-lightning:free",
        "name": "NVIDIA: Nemotron 3.5 Lightning (Free)",
        "context_length": 131072,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "mistralai/mistral-large",
        "name": "Mistral: Mistral Large",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
    },
)


class OpenRouterChatProvider(OpenAICompatibleChatProvider):
    provider_name = "openrouter"
    display_name = "OpenRouter AI"
    description = "Access hundreds of open & commercial models via openrouter.ai"
    base_url = _BASE_URL
    auth_endpoint = f"{_BASE_URL}/auth/key"
    default_model = "meta-llama/llama-3.3-70b-instruct"
    preferred_models = tuple(m["id"] for m in DEFAULT_OPENROUTER_MODELS)
    fallback_models = DEFAULT_OPENROUTER_MODELS
    auth_type = "api_key"
    api_key_placeholder = "sk-or-v1-..."
    model_mode = "curated"
    validate_on_refresh = True
    suggested_models = (
        {"id": "meta-llama/llama-3.3-70b-instruct", "label": "meta-llama/llama-3.3-70b-instruct"},
        {"id": "deepseek/deepseek-chat", "label": "deepseek/deepseek-chat"},
        {"id": "google/gemma-4-26b-a4b-it:free", "label": "google/gemma-4-26b-a4b-it:free"},
        {"id": "nvidia/nemotron-3.5-lightning:free", "label": "nvidia/nemotron-3.5-lightning:free"},
    )
    docs_url = "https://openrouter.ai/docs"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers.update({
            "HTTP-Referer": "https://github.com/lhotakj/kinetiqo",
            "X-Title": "Kinetiqo",
            "X-OpenRouter-Title": "Kinetiqo",
        })
        return headers

    @staticmethod
    def _parse_model_item(item: dict[str, Any]) -> dict[str, Any]:
        mid = item.get("id", "")
        name = item.get("name") or mid
        context_len = item.get("context_length") or 128000
        arch = item.get("architecture") or {}
        modality = arch.get("modality", "")
        supports_vision = "image" in modality.lower() or "multimodal" in modality.lower()
        pricing = item.get("pricing") or {}
        supported_params = item.get("supported_parameters") or []
        top_provider = item.get("top_provider") or {}
        is_embedding = "embed" in mid.lower() or "embedding" in modality.lower()
        supports_tools = ("tools" in supported_params or not supported_params) and not is_embedding
        return {
            "id": mid,
            "name": name,
            "display_name": name,
            "context_length": context_len,
            "supports_tools": supports_tools,
            "supports_vision": supports_vision,
            "pricing": pricing,
            "description": item.get("description") or "",
            "max_output_tokens": top_provider.get("max_completion_tokens") or item.get("max_completion_tokens"),
            "rate_limits": item.get("rate_limits"),
            "request_limits": item.get("per_request_limits"),
            "is_embedding": is_embedding,
        }

    def list_models(self) -> list[ChatProviderModel]:
        """Return configured models for this athlete, or curated defaults (excluding embedding models)."""
        raw_list = self.configured_models if self.configured_models else list(DEFAULT_OPENROUTER_MODELS)
        result = []
        for m in raw_list:
            mid = m.get("id", "")
            if "embed" in mid.lower() or m.get("is_embedding"):
                continue
            result.append(
                ChatProviderModel(
                    id=mid,
                    display_name=m.get("name") or mid,
                    supports_tools=m.get("supports_tools", True),
                    supports_vision=m.get("supports_vision", False),
                )
            )
        return result

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate an OpenRouter model ID by fetching its metadata from OpenRouter."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        clean_lower = clean_id.lower()
        if "embed" in clean_lower:
            raise ValueError(
                f"'{clean_id}' is an embedding model, not a generative chat model. "
                "OpenRouter requires chat instruction models (such as meta-llama/llama-3.3-70b-instruct, deepseek/deepseek-chat, or google/gemma-4-26b-a4b-it:free) for AI Chat."
            )

        with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            cat_url = f"{_BASE_URL}/models"
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

            # 1. Exact match (case-insensitive)
            for item in models:
                mid = (item.get("id") or "").lower()
                if mid == clean_lower:
                    parsed = self._parse_model_item(item)
                    if parsed.get("is_embedding"):
                        raise ValueError(
                            f"'{clean_id}' is an embedding model and cannot be used for text chat. Please choose a generative chat model."
                        )
                    return parsed

            # 2. Check if a suffix (like :free or other variant) was specified and base model exists
            if ":" in clean_lower:
                base_part = clean_lower.split(":", 1)[0]
                for item in models:
                    mid = (item.get("id") or "").lower()
                    if mid == base_part:
                        matched_id = item.get("id", base_part)
                        err = LookupError(
                            f"Model '{clean_id}' was not found in OpenRouter. "
                            f"OpenRouter does not currently offer a free tier (:free) for this model, but the base model '{matched_id}' is available."
                        )
                        setattr(err, "suggestion", matched_id)
                        raise err

            # 3. Fuzzy / partial candidate suggestions
            candidates = [
                item.get("id")
                for item in models
                if item.get("id") and (
                    clean_lower in item.get("id", "").lower()
                    or item.get("id", "").lower() in clean_lower
                )
            ]
            if candidates:
                best_suggestion = candidates[0]
                err = LookupError(
                    f"Model '{clean_id}' was not found in OpenRouter. Did you mean '{best_suggestion}'?"
                )
                setattr(err, "suggestion", best_suggestion)
                raise err

        raise LookupError(f"Model '{clean_id}' was not found in OpenRouter.")
