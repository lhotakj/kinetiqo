"""MagnetAPI REST adapter using httpx and OpenAI-compatible streaming SSE."""

import logging
from typing import Any, Optional

import httpx

from kinetiqo.chat.providers.openai_compatible import OpenAICompatibleChatProvider

_BASE_URL = "https://api.magnetapi.org/v1"
logger = logging.getLogger("kinetiqo.chat.magnetapi")

DEFAULT_MAGNETAPI_MODELS = (
    {
        "id": "power-ai",
        "name": "MagnetAPI: Power AI (Auto Managed)",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
        "pricing": {"prompt": "varies", "completion": "varies"},
        "description": "High-performance auto-managed coding & reasoning destination",
    },
    {
        "id": "gpt-6.1-sol",
        "name": "OpenAI: ChatGPT 6.1 SOL",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Frontier coding and reasoning model with Extra High reasoning effort",
    },
    {
        "id": "gpt-6-astra",
        "name": "OpenAI: ChatGPT 6 Astra",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Premium multimodal and reasoning model for software engineering",
    },
    {
        "id": "claude-opus-5-5",
        "name": "Anthropic: Claude Opus 5.5",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Next-generation flagship reasoning and complex synthesis model",
    },
    {
        "id": "claude-sonnet-5-5",
        "name": "Anthropic: Claude Sonnet 5.5",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Balanced high-performance model for analysis, coaching, and tools",
    },
    {
        "id": "claude-fable-5-1",
        "name": "Anthropic: Claude Fable 5.1",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Specialized Claude selection for deep coding and code reviews",
    },
    {
        "id": "deepseek-flash",
        "name": "DeepSeek: DeepSeek V4.1 Flash",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
        "description": "Low-latency, highly cost-effective coding and reasoning model",
    },
    {
        "id": "gpt-daybreak-blue-latest",
        "name": "OpenAI: ChatGPT Daybreak Blue",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Latest ChatGPT Daybreak multimodal checkpoint",
    },
)


class MagnetAPIChatProvider(OpenAICompatibleChatProvider):
    provider_name = "magnetapi"
    display_name = "MagnetAPI"
    description = "Official MagnetAPI gateway with auto-discovered generation models (magnetapi.org)"
    base_url = _BASE_URL
    default_model = "power-ai"
    preferred_models = tuple(m["id"] for m in DEFAULT_MAGNETAPI_MODELS)
    fallback_models = DEFAULT_MAGNETAPI_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter MagnetAPI key (from magnetapi.org)"
    model_mode = "discovered"
    validate_on_refresh = True
    suggested_models = (
        {"id": "power-ai", "label": "power-ai (Auto Managed)"},
        {"id": "gpt-6.1-sol", "label": "gpt-6.1-sol"},
        {"id": "claude-sonnet-5-5", "label": "claude-sonnet-5-5"},
        {"id": "deepseek-flash", "label": "deepseek-flash"},
    )
    docs_url = "https://magnetapi.org/docs"
