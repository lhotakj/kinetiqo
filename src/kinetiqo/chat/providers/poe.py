"""Poe REST adapter using its OpenAI-compatible streaming chat completions API."""

import logging
from typing import Any
from urllib.parse import quote

import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
)
from kinetiqo.chat.models import ChatProviderModel
from kinetiqo.chat.providers.kilo import KiloChatProvider

_BASE_URL = "https://api.poe.com/v1"
_API_URL = "https://api.poe.com"
logger = logging.getLogger("kinetiqo.chat.poe")


class PoeChatProvider(KiloChatProvider):
    """OpenAI-compatible Poe gateway for configured Poe bot handles."""

    provider_name = "poe"
    base_url = _BASE_URL
    default_model = ""
    preferred_models: tuple[str, ...] = ()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Kinetiqo-Fitness-AI",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        if response.status_code in (401, 403):
            raise ChatAuthenticationError("Poe rejected the API key.")
        if response.status_code in (402, 429):
            raise ChatRateLimitError("Poe account balance or request limit was reached.")
        if response.status_code >= 500:
            raise ChatProviderUnavailableError("Poe is temporarily unavailable.")
        raise ChatProviderResponseError(f"Poe chat completion failed (HTTP {response.status_code}).")

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Resolve a Poe bot handle and retain only metadata supplied by Poe."""
        handle = model_id.strip()
        if not handle:
            raise ValueError("Poe bot handle cannot be empty.")

        url = f"{_API_URL}/bots/{quote(handle, safe='')}"
        try:
            with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
                response = client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise ChatProviderUnavailableError("Poe bot lookup timed out.") from exc
        except httpx.RequestError as exc:
            raise ChatProviderUnavailableError("Poe bot lookup failed.") from exc

        if response.status_code in (401, 403):
            raise ChatAuthenticationError("Poe rejected the API key.")
        if response.status_code == 404:
            raise LookupError(f"Poe bot '{handle}' was not found or is unavailable.")
        if response.status_code == 429:
            raise ChatRateLimitError("Poe API rate limit exceeded.")
        if response.status_code >= 500:
            raise ChatProviderUnavailableError("Poe is temporarily unavailable.")
        if not response.is_success:
            raise ChatProviderResponseError(f"Poe bot lookup failed (HTTP {response.status_code}).")

        payload = response.json()
        bot = payload.get("bot", payload) if isinstance(payload, dict) else {}
        if not isinstance(bot, dict):
            raise ChatProviderResponseError("Poe returned an invalid bot response.")

        canonical_handle = str(bot.get("handle") or bot.get("id") or handle).strip()
        result: dict[str, Any] = {
            "id": canonical_handle,
            "name": str(bot.get("display_name") or bot.get("name") or canonical_handle),
            "display_name": str(bot.get("display_name") or bot.get("name") or canonical_handle),
            "supports_tools": True,
            "supports_vision": False,
        }
        for key in ("context_length", "max_output_tokens", "pricing", "rate_limits", "request_limits", "description"):
            if bot.get(key) is not None:
                result[key] = bot[key]
        return result

    def list_models(self) -> list[ChatProviderModel]:
        """Return explicitly configured Poe bot handles; Poe has no assumed default bot."""
        models = []
        for item in self.configured_models:
            handle = str(item.get("id") or "").strip()
            if not handle:
                continue
            models.append(ChatProviderModel(
                id=handle,
                display_name=str(item.get("display_name") or item.get("name") or handle),
                supports_tools=bool(item.get("supports_tools", True)),
                supports_vision=bool(item.get("supports_vision", False)),
            ))
        return models
