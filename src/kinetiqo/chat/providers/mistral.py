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
from kinetiqo.chat.providers.base import BaseChatProvider

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


class MistralChatProvider(BaseChatProvider):
    provider_name = "mistral"
    display_name = "Mistral AI"
    description = "Official Mistral AI API with frontier European models"
    base_url = _BASE_URL
    default_model = "mistral-small-latest"
    deprecated_models = DEPRECATED_MODELS
    preferred_models = PREFERRED_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter Mistral API key"
    model_mode = "discovered"
    suggested_models = ()
    docs_url = "https://docs.mistral.ai/"

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
            "Accept": "application/json",
            "User-Agent": "Kinetiqo-Fitness-AI",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        err_body = ""
        try:
            if hasattr(response, "read"):
                raw = response.read()
                err_body = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            elif hasattr(response, "text"):
                err_body = response.text
        except Exception:
            pass

        err_msg = ""
        err_code = ""
        if err_body:
            try:
                payload = json.loads(err_body)
                if isinstance(payload, dict):
                    err_obj = payload.get("error")
                    if isinstance(err_obj, dict):
                        err_msg = err_obj.get("message") or ""
                        err_code = err_obj.get("code") or err_obj.get("type") or ""
                    elif isinstance(err_obj, str):
                        err_msg = err_obj
                    elif payload.get("message"):
                        err_msg = str(payload["message"])
            except Exception:
                pass

        summary_detail = err_msg or err_code or (err_body[:200].strip() if err_body else "")

        if response.status_code in (401, 403):
            logger.warning(
                "Mistral AI rejected key: http_status=%d code=%s body=%s",
                response.status_code,
                err_code or "-",
                err_body[:500],
            )
            detail = f": {summary_detail}" if summary_detail else ". Check your API key at console.mistral.ai."
            raise ChatAuthenticationError(
                f"Mistral AI access rejected (HTTP {response.status_code}){detail}"
            )
        if response.status_code == 402:
            logger.warning("Mistral AI returned 402 (Payment Required): %s", err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"Mistral AI account has insufficient credits or unpaid subscription{detail}")
        if response.status_code == 429:
            logger.warning("Mistral AI rate limit hit: http_status=429 %s", err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"Mistral AI rate limit or concurrency quota exceeded{detail}")
        if 500 <= response.status_code < 600:
            logger.warning("Mistral AI upstream error: http_status=%d %s", response.status_code, err_body[:500])
            raise ChatProviderUnavailableError("Mistral AI is temporarily unavailable.")

        logger.warning("Mistral AI error response: http_status=%d body=%s", response.status_code, err_body[:500])
        detail = f": {summary_detail}" if summary_detail else "."
        raise ChatProviderResponseError(f"Mistral AI returned an error (HTTP {response.status_code}){detail}")

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

        url = f"{self.base_url}/chat/completions"
        logger.debug(
            "Mistral AI stream starting: model=%s history_messages=%d tools_provided=%d",
            model_id,
            len(history),
            len(tools or []),
        )

        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 64
                any_text_streamed = False
                seen_tool_signatures: list[str] = []

                # Determine if this model supports tools
                model_meta = next((m for m in self.configured_models if m.get("id") == model_id), None)
                model_supports_tools = model_meta.get("supports_tools", True) if model_meta else True
                if "embed" in model_id.lower():
                    model_supports_tools = False

                for turn_idx in range(max_turns):
                    body: dict[str, Any] = {
                        "model": model_id,
                        "messages": messages,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    }
                    if tools and model_supports_tools:
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
                                result_data["_directive"] = (
                                    "You have queried this identical data multiple times. "
                                    "Do not call this tool again with identical parameters; synthesize your answer now."
                                )

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
                        logger.info("Mistral AI turn %d executed %d tool calls; looping", turn_idx + 1, len(executed_tool_messages))
                        continue

                    # Final turn or no tools called
                    if last_usage:
                        yield StreamEvent(
                            "usage",
                            input_tokens=last_usage.get("prompt_tokens"),
                            output_tokens=last_usage.get("completion_tokens"),
                        )
                    logger.info("Mistral AI stream finished: model=%s turns=%d text_len=%d", model_id, turn_idx + 1, len(accumulated_content))
                    break

        except httpx.TimeoutException as exc:
            logger.warning("Mistral AI stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning("Mistral AI stream network error: model=%s error=%s", model_id, exc)
            raise ChatProviderUnavailableError() from exc

