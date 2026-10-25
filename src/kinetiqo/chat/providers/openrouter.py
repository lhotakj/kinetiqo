"""OpenRouter REST adapter using httpx and OpenAI-compatible streaming SSE."""

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
    ChatSafetyBlockedError,
    ChatTimeoutError,
)
from kinetiqo.chat.models import ChatProviderModel, StreamEvent
from kinetiqo.chat.providers.base import BaseChatProvider

_BASE_URL = "https://openrouter.ai/api/v1"
logger = logging.getLogger("kinetiqo.chat.openrouter")

DEFAULT_OPENROUTER_MODELS = (
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Anthropic: Claude 3.5 Sonnet",
        "context_length": 200000,
        "supports_tools": True,
        "supports_vision": True,
    },
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
        "id": "mistralai/mistral-large-2411",
        "name": "Mistral: Mistral Large 2411",
        "context_length": 128000,
        "supports_tools": True,
        "supports_vision": False,
    },
    {
        "id": "nvidia/nemotron-3.5-embed-1b:free",
        "name": "Nvidia: Nemotron 3.5 1B (Free)",
        "context_length": 131072,
        "supports_tools": False,
        "supports_vision": False,
    },
)


class OpenRouterChatProvider(BaseChatProvider):
    provider_name = "openrouter"
    default_model = "anthropic/claude-3.5-sonnet"
    preferred_models = tuple(m["id"] for m in DEFAULT_OPENROUTER_MODELS)

    def __init__(
        self,
        api_key: str,
        client_factory: Any = httpx.Client,
        configured_models: list[dict[str, Any]] | None = None,
    ):
        super().__init__(api_key, client_factory or httpx.Client)
        self.configured_models = configured_models or []

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lhotakj/kinetiqo",
            "X-Title": "Kinetiqo",
            "X-OpenRouter-Title": "Kinetiqo",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401 or response.status_code == 403:
            logger.warning("OpenRouter API rejected key: http_status=%d", response.status_code)
            raise ChatAuthenticationError()
        if response.status_code == 402:
            logger.warning("OpenRouter API returned 402 (Payment Required / Credit limit)")
            raise ChatRateLimitError("OpenRouter account has insufficient credits.")
        if response.status_code == 429:
            logger.warning("OpenRouter API rate limit hit: http_status=429")
            raise ChatRateLimitError("OpenRouter rate limit or quota exceeded.")
        if 500 <= response.status_code < 600:
            logger.warning("OpenRouter upstream error: http_status=%d", response.status_code)
            raise ChatProviderUnavailableError()
        if not response.is_success:
            logger.warning("OpenRouter error response: http_status=%d", response.status_code)
            raise ChatProviderResponseError()

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate an OpenRouter model ID by fetching its metadata from OpenRouter."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            # 1. Try single model endpoint: GET /api/v1/model/{author}/{slug}
            single_url = f"{_BASE_URL}/model/{clean_id}"
            try:
                resp = client.get(single_url, headers=self._headers())
                if resp.status_code == 200:
                    payload = resp.json()
                    item = payload.get("data") or payload
                    if isinstance(item, dict) and item.get("id"):
                        return self._parse_model_item(item)
            except Exception as e:
                logger.debug("Single model endpoint check failed for '%s': %s", clean_id, e)

            # 2. Fallback: Search /api/v1/models catalog
            cat_url = f"{_BASE_URL}/models"
            resp = client.get(cat_url, headers=self._headers())
            self._raise_for_status(resp)
            payload = resp.json()
            models = payload.get("data") or []
            clean_lower = clean_id.lower()
            for item in models:
                mid = (item.get("id") or "").lower()
                if mid == clean_lower:
                    return self._parse_model_item(item)

        raise LookupError(f"Model '{clean_id}' was not found in OpenRouter.")

    @staticmethod
    def _parse_model_item(item: dict[str, Any]) -> dict[str, Any]:
        mid = item.get("id", "")
        name = item.get("name") or mid
        context_len = item.get("context_length") or 128000
        arch = item.get("architecture") or {}
        modality = arch.get("modality", "")
        supports_vision = "image" in modality.lower() or "multimodal" in modality.lower()
        pricing = item.get("pricing") or {}
        return {
            "id": mid,
            "name": name,
            "display_name": name,
            "context_length": context_len,
            "supports_tools": True,
            "supports_vision": supports_vision,
            "pricing": pricing,
        }

    def list_models(self) -> list[ChatProviderModel]:
        """Return configured models for this athlete, or curated defaults."""
        raw_list = self.configured_models if self.configured_models else list(DEFAULT_OPENROUTER_MODELS)
        result = []
        for m in raw_list:
            result.append(
                ChatProviderModel(
                    id=m["id"],
                    display_name=m.get("name") or m["id"],
                    supports_tools=m.get("supports_tools", True),
                    supports_vision=m.get("supports_vision", False),
                )
            )
        return result

    def stream(
        self,
        model_id: str,
        system_instruction: str,
        history: list[dict[str, str]],
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any = None,
    ) -> Iterator[StreamEvent]:
        """Stream completion events with OpenAI-compatible multi-turn tool calling."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for item in history:
            role = item["role"]
            content = item["content"]
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        url = f"{_BASE_URL}/chat/completions"
        logger.debug("OpenRouter stream starting: model=%s history_messages=%d tools_provided=%d", model_id, len(history), len(tools or []))

        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 64
                any_text_streamed = False
                seen_tool_signatures: list[str] = []

                for turn_idx in range(max_turns):
                    body: dict[str, Any] = {
                        "model": model_id,
                        "messages": messages,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    if tools:
                        body["tools"] = tools
                        if turn_idx >= (max_turns - 1):
                            body["tool_choice"] = "none"

                    accumulated_content = ""
                    accumulated_tool_calls: dict[int, dict[str, Any]] = {}
                    last_usage: dict[str, Any] | None = None

                    with client.stream("POST", url, headers=self._headers(), json=body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            usage = chunk.get("usage")
                            if usage:
                                last_usage = usage

                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}

                            # 1. Text deltas
                            text_piece = delta.get("content")
                            if text_piece:
                                accumulated_content += text_piece
                                yield StreamEvent("text_delta", text=text_piece)
                                any_text_streamed = True

                            # 2. Tool calls delta
                            raw_tool_deltas = delta.get("tool_calls") or []
                            for tc in raw_tool_deltas:
                                idx = tc.get("index", 0)
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {
                                        "id": tc.get("id", f"call_{idx}"),
                                        "name": "",
                                        "arguments": "",
                                    }
                                if tc.get("id"):
                                    accumulated_tool_calls[idx]["id"] = tc["id"]
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    accumulated_tool_calls[idx]["name"] += fn["name"]
                                if fn.get("arguments"):
                                    accumulated_tool_calls[idx]["arguments"] += fn["arguments"]

                    # If model requested tools, execute them and proceed to next turn
                    if accumulated_tool_calls and tool_executor is not None and turn_idx < (max_turns - 1):
                        executed_tool_messages: list[dict[str, Any]] = []
                        assistant_tool_calls: list[dict[str, Any]] = []

                        for _, call_info in sorted(accumulated_tool_calls.items()):
                            fn_name = call_info["name"]
                            raw_args = call_info["arguments"]
                            try:
                                fn_args = json.loads(raw_args) if raw_args else {}
                            except json.JSONDecodeError:
                                fn_args = {}

                            call_id = call_info["id"]
                            assistant_tool_calls.append({
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": fn_name,
                                    "arguments": raw_args,
                                },
                            })

                            sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
                            seen_tool_signatures.append(sig)
                            yield StreamEvent("tool_call", tool=fn_name, arguments=fn_args)
                            result_data, _ = tool_executor(fn_name, fn_args)

                            if seen_tool_signatures.count(sig) >= 3 and isinstance(result_data, dict):
                                result_data["_directive"] = "You have queried this identical data multiple times. Do not call this tool again with identical parameters; synthesize your answer now."

                            yield StreamEvent("tool_result", tool=fn_name, tool_data=result_data)
                            executed_tool_messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": fn_name,
                                "content": json.dumps(result_data, default=str),
                            })

                        messages.append({
                            "role": "assistant",
                            "content": accumulated_content or None,
                            "tool_calls": assistant_tool_calls,
                        })
                        messages.extend(executed_tool_messages)
                        logger.info("OpenRouter turn %d executed %d tool calls; looping", turn_idx + 1, len(executed_tool_messages))
                        continue

                    # Final turn or no tools called
                    if last_usage:
                        yield StreamEvent(
                            "usage",
                            input_tokens=last_usage.get("prompt_tokens"),
                            output_tokens=last_usage.get("completion_tokens"),
                        )
                    logger.info("OpenRouter stream finished: model=%s turns=%d text_len=%d", model_id, turn_idx + 1, len(accumulated_content))
                    break

        except httpx.TimeoutException as exc:
            logger.warning("OpenRouter stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning("OpenRouter stream network error: model=%s error=%s", model_id, exc)
            raise ChatProviderUnavailableError() from exc
