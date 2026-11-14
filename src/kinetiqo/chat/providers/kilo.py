"""Kilo AI Gateway REST adapter using httpx and OpenAI-compatible streaming SSE."""

import logging
from typing import Any, Optional

import httpx

from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://api.kilo.ai/api/gateway"
logger = logging.getLogger("kinetiqo.chat.kilo")

DEFAULT_KILO_MODELS = (
    {
        "id": "kilo-auto/free",
        "name": "Kilo: Auto Free Tier (Free)",
        "context_length": 262144,
        "supports_tools": True,
        "supports_vision": True,
        "pricing": {"input": "0.0", "output": "0.0"},
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Meta: Llama 3.3 70B Instruct",
        "context_length": 131072,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek: DeepSeek R1",
        "context_length": 64000,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "qwen/qwen-2.5-coder-32b-instruct",
        "name": "Qwen: Qwen 2.5 Coder 32B Instruct",
        "context_length": 131072,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "anthropic/claude-3.5-haiku",
        "name": "Anthropic: Claude 3.5 Haiku",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI: GPT-4o Mini",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
    },
)


class KiloChatProvider(OpenAICompatibleChatProvider):
    provider_name = "kilo"
    display_name = "Kilo AI Gateway"
    description = "High-performance AI Gateway with auto-routing and free tier models"
    base_url = _BASE_URL
    default_model = "kilo-auto/free"
    preferred_models = tuple(m["id"] for m in DEFAULT_KILO_MODELS)
    fallback_models = DEFAULT_KILO_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter Kilo AI API key"
    model_mode = "curated"
    validate_on_refresh = True
    suggested_models = (
        {"id": "kilo-auto/free", "label": "kilo-auto/free (Free)"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "label": "meta-llama/llama-3.3-70b-instruct"},
        {"id": "deepseek/deepseek-r1", "label": "deepseek/deepseek-r1"},
        {"id": "google/gemini-2.5-flash", "label": "google/gemini-2.5-flash"},
    )
    docs_url = "https://kilo.ai/docs"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = "https://github.com/lhotakj/kinetiqo"
        headers["X-Title"] = "Kinetiqo"
        return headers

    def list_models(self) -> list[ChatProviderModel]:
        """Return configured models for this athlete, or curated defaults (excluding embedding models)."""
        raw_list = self.configured_models if self.configured_models else list(DEFAULT_KILO_MODELS)
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
