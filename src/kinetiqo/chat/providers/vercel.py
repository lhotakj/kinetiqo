"""Vercel AI Gateway REST adapter using httpx and OpenAI-compatible streaming SSE."""

import logging
from typing import Any, Optional

import httpx

from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://ai-gateway.vercel.sh/v1"
logger = logging.getLogger("kinetiqo.chat.vercel")

DEFAULT_VERCEL_MODELS = (
    {
        "id": "nvidia/nemotron-3.5-lightning-free",
        "name": "NVIDIA: Nemotron 3.5 Lightning (Free)",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "poolside/laguna-s-2.1-free",
        "name": "Poolside: Laguna S 2.1 (Free)",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "moonshotai/kimi-k2.6",
        "name": "Moonshot AI: Kimi K2.6",
        "context_length": 262000,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "meta/llama-3.3-70b",
        "name": "Meta: Llama 3.3 70B",
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
        "id": "anthropic/claude-haiku-4.5",
        "name": "Anthropic: Claude Haiku 4.5",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "openai/gpt-4o",
        "name": "OpenAI: GPT-4o",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
    },
)


class VercelChatProvider(OpenAICompatibleChatProvider):
    provider_name = "vercel"
    display_name = "Vercel AI Gateway"
    description = "Fast unified gateway to 100+ open & frontier models via Vercel AI Gateway"
    base_url = _BASE_URL
    default_model = "moonshotai/kimi-k2.6"
    preferred_models = tuple(m["id"] for m in DEFAULT_VERCEL_MODELS)
    fallback_models = DEFAULT_VERCEL_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter Vercel AI Gateway key"
    model_mode = "curated"
    validate_on_refresh = True
    suggested_models = (
        {"id": "nvidia/nemotron-3.5-lightning-free", "label": "nvidia/nemotron-3.5-lightning-free (Free)"},
        {"id": "moonshotai/kimi-k2.6", "label": "moonshotai/kimi-k2.6"},
        {"id": "meta/llama-3.3-70b", "label": "meta/llama-3.3-70b"},
        {"id": "deepseek/deepseek-r1", "label": "deepseek/deepseek-r1"},
    )
    docs_url = "https://vercel.com/docs/ai-gateway"

    def list_models(self) -> list[ChatProviderModel]:
        """Return configured models for this athlete, or curated defaults (excluding embedding models)."""
        raw_list = self.configured_models if self.configured_models else list(DEFAULT_VERCEL_MODELS)
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
