"""PayPerQ (PPQ.AI) REST adapter using httpx and OpenAI-compatible streaming SSE."""

import logging
from typing import Any, Optional

import httpx

from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://api.ppq.ai/v1"
logger = logging.getLogger("kinetiqo.chat.payperq")

DEFAULT_PAYPERQ_MODELS = (
    {
        "id": "auto",
        "name": "PayPerQ: Smart Router (Auto)",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
        "pricing": {"prompt": "varies", "completion": "varies"},
    },
    {
        "id": "autoclaw/eco",
        "name": "PayPerQ: AutoClaw Eco (Low Cost)",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "pricing": {"prompt": "low", "completion": "low"},
    },
    {
        "id": "claude-sonnet-4.6",
        "name": "Anthropic: Claude Sonnet 4.6",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek: DeepSeek R1",
        "context_length": 64000,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "openai/gpt-4o",
        "name": "OpenAI: GPT-4o",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Google: Gemini 2.5 Flash",
        "context_length": 1048576,
        "supports_tools": True,
        "supports_vision": True,
    },
)


class PayPerQChatProvider(OpenAICompatibleChatProvider):
    provider_name = "payperq"
    display_name = "PayPerQ"
    description = "Subscription-free pay-per-query AI gateway to 100+ frontier & open models via PayPerQ (ppq.ai)"
    base_url = _BASE_URL
    default_model = "auto"
    preferred_models = tuple(m["id"] for m in DEFAULT_PAYPERQ_MODELS)
    fallback_models = DEFAULT_PAYPERQ_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter PayPerQ API key (ppq_...)"
    model_mode = "discovered"
    validate_on_refresh = True
    suggested_models = (
        {"id": "auto", "label": "auto (Smart Router)"},
        {"id": "autoclaw/eco", "label": "autoclaw/eco (Eco Router)"},
        {"id": "claude-sonnet-4.6", "label": "claude-sonnet-4.6"},
        {"id": "deepseek/deepseek-r1", "label": "deepseek/deepseek-r1"},
        {"id": "openai/gpt-4o", "label": "openai/gpt-4o"},
        {"id": "google/gemini-2.5-flash", "label": "google/gemini-2.5-flash"},
    )
    docs_url = "https://ppq.ai/chat"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["HTTP-Referer"] = "https://github.com/lhotakj/kinetiqo"
        headers["X-Title"] = "Kinetiqo"
        return headers
