"""Anthropic Claude REST adapter using httpx and Anthropic Messages streaming API."""

import json
import logging
from collections.abc import Iterator
from typing import Any, Callable

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

_BASE_URL = "https://api.anthropic.com/v1"
_ANTHROPIC_VERSION = "2023-06-01"
logger = logging.getLogger("kinetiqo.chat.anthropic")

DEPRECATED_MODELS = frozenset({
    "claude-1",
    "claude-2",
    "claude-2.0",
    "claude-2.1",
    "claude-instant-1",
    "claude-instant-1.2",
})

PREFERRED_MODELS = (
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-20241022",
    "claude-3-5-haiku-latest",
    "claude-3-opus-20240229",
    "claude-3-opus-latest",
    "claude-3-haiku-20240307",
    "claude-3-sonnet-20240229",
)

DEFAULT_ANTHROPIC_MODELS = (
    {
        "id": "claude-3-7-sonnet-20250219",
        "name": "Claude 3.7 Sonnet",
        "context_length": 200000,
        "max_output_tokens": 8192,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Hybrid reasoning frontier model for coding, analysis, and complex reasoning",
    },
    {
        "id": "claude-3-5-sonnet-20241022",
        "name": "Claude 3.5 Sonnet",
        "context_length": 200000,
        "max_output_tokens": 8192,
        "supports_tools": True,
        "supports_vision": True,
        "description": "High-intelligence flagship model with exceptional reasoning, coding, and vision",
    },
    {
        "id": "claude-3-5-haiku-20241022",
        "name": "Claude 3.5 Haiku",
        "context_length": 200000,
        "max_output_tokens": 8192,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Ultra-fast, cost-effective model for high-throughput and conversational tasks",
    },
    {
        "id": "claude-3-opus-20240229",
        "name": "Claude 3 Opus",
        "context_length": 200000,
        "max_output_tokens": 4096,
        "supports_tools": True,
        "supports_vision": True,
        "description": "Powerful model for highly complex analysis and domain synthesis",
    },
)


class AnthropicChatProvider(BaseChatProvider):
    provider_name = "anthropic"
    display_name = "Anthropic Claude"
    description = "Official Anthropic API with frontier Claude models"
    base_url = _BASE_URL
    default_model = "claude-3-5-sonnet-20241022"
    deprecated_models = DEPRECATED_MODELS
    preferred_models = PREFERRED_MODELS
    auth_type = "api_key"
    api_key_placeholder = "Enter Anthropic API key (sk-ant-...)"
    model_mode = "discovered"
    suggested_models = ()
    docs_url = "https://docs.anthropic.com/"

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
            "x-api-key": (self.api_key or "").strip(),
            "anthropic-version": _ANTHROPIC_VERSION,
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
        err_type = ""
        if err_body:
            try:
                payload = json.loads(err_body)
                if isinstance(payload, dict):
                    err_obj = payload.get("error")
                    if isinstance(err_obj, dict):
                        err_msg = str(err_obj.get("message") or "")
                        err_type = str(err_obj.get("type") or "")
                    elif isinstance(err_obj, str):
                        err_msg = err_obj
                    elif payload.get("message"):
                        err_msg = str(payload["message"])
            except Exception:
                pass

        summary_detail = err_msg or err_type or (err_body[:200].strip() if err_body else "")

        if response.status_code in (401, 403):
            logger.warning(
                "Anthropic rejected key: http_status=%d type=%s body=%s",
                response.status_code,
                err_type or "-",
                err_body[:500],
            )
            detail = f": {summary_detail}" if summary_detail else ". Check your API key at console.anthropic.com."
            raise ChatAuthenticationError(
                f"Anthropic access rejected (HTTP {response.status_code}){detail}"
            )

        if response.status_code == 429:
            logger.warning("Anthropic rate limit hit: http_status=429 %s", err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"Anthropic rate limit or concurrency quota exceeded{detail}")

        if response.status_code in (400, 402) and ("credit" in err_msg.lower() or "balance" in err_msg.lower()):
            logger.warning("Anthropic credit balance error: http_status=%d %s", response.status_code, err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"Anthropic account has insufficient credit balance{detail}")

        if response.status_code == 529 or 500 <= response.status_code < 600:
            logger.warning("Anthropic upstream error: http_status=%d %s", response.status_code, err_body[:500])
            raise ChatProviderUnavailableError("Anthropic is temporarily unavailable or overloaded.")

        logger.warning("Anthropic error response: http_status=%d body=%s", response.status_code, err_body[:500])
        detail = f": {summary_detail}" if summary_detail else "."
        raise ChatProviderResponseError(f"Anthropic returned an error (HTTP {response.status_code}){detail}")

    def _parse_model_item(self, item: dict[str, Any]) -> dict[str, Any]:
        mid = str(item.get("id") or "").strip()
        display_name = str(item.get("display_name") or item.get("name") or mid).strip()

        lower_id = mid.lower()
        is_embedding = "embed" in lower_id
        is_deprecated = mid in self.deprecated_models

        # Determine output token limits
        if "3-7" in lower_id or "3.7" in lower_id:
            max_tokens = 8192
            desc = "Hybrid reasoning frontier model for coding, analysis, and complex reasoning"
        elif "3-5" in lower_id or "3.5" in lower_id:
            max_tokens = 8192
            if "haiku" in lower_id:
                desc = "Ultra-fast, cost-effective model for high-throughput and conversational tasks"
            else:
                desc = "High-intelligence flagship model with exceptional reasoning, coding, and vision"
        elif "opus" in lower_id:
            max_tokens = 4096
            desc = "Powerful model for highly complex analysis and domain synthesis"
        else:
            max_tokens = 4096
            desc = "Anthropic Claude generation model"

        context_len = item.get("context_length") or item.get("max_context_length") or 200000
        supports_tools = bool(item.get("supports_tools", True)) and not is_embedding and not is_deprecated
        supports_vision = bool(item.get("supports_vision", True)) and not is_embedding and not is_deprecated

        return {
            "id": mid,
            "name": display_name,
            "display_name": display_name,
            "context_length": context_len,
            "supports_tools": supports_tools,
            "supports_vision": supports_vision,
            "description": item.get("description") or desc,
            "is_chat": not is_embedding and not is_deprecated,
            "is_embedding": is_embedding,
            "pricing": item.get("pricing"),
            "max_output_tokens": item.get("max_tokens") or item.get("max_output_tokens") or max_tokens,
            "rate_limits": item.get("rate_limits"),
            "request_limits": item.get("request_limits"),
        }

    def list_models(self) -> list[ChatProviderModel]:
        """Discover models directly from Anthropic /v1/models endpoint."""
        url = f"{self.base_url}/models?limit=100"
        try:
            with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
                resp = client.get(url, headers=self._headers())
                self._raise_for_status(resp)
                payload = resp.json()
                data_val = payload.get("data")
                if isinstance(data_val, list):
                    models = data_val
                elif isinstance(payload, list):
                    models = payload
                else:
                    models = []
        except (httpx.TimeoutException, httpx.RequestError, ChatProviderUnavailableError) as exc:
            logger.warning("Anthropic models endpoint unreachable; using curated fallback models: %s", exc)
            models = list(DEFAULT_ANTHROPIC_MODELS)

        if not models:
            models = list(DEFAULT_ANTHROPIC_MODELS)

        result: list[ChatProviderModel] = []
        seen_ids: set[str] = set()

        for item in models:
            if not isinstance(item, dict):
                continue
            parsed = self._parse_model_item(item)
            mid = parsed["id"]
            if not mid or mid in seen_ids:
                continue
            if not parsed["is_chat"] or parsed["is_embedding"]:
                continue
            seen_ids.add(mid)
            result.append(
                ChatProviderModel(
                    id=mid,
                    display_name=parsed["display_name"],
                    context_length=parsed["context_length"],
                    supports_tools=parsed["supports_tools"],
                    supports_vision=parsed["supports_vision"],
                    pricing=parsed["pricing"],
                    max_output_tokens=parsed["max_output_tokens"],
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
        logger.info("Anthropic model discovery completed: available_models=%d", len(result))
        return result

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate an Anthropic model identifier."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        clean_lower = clean_id.lower()
        if "embed" in clean_lower:
            raise ValueError(
                f"'{clean_id}' is an embedding model and cannot be used for text chat. "
                "Please choose a generative model (such as claude-3-5-sonnet-20241022)."
            )
        if clean_id in self.deprecated_models:
            raise ValueError(f"'{clean_id}' is deprecated. Please choose a modern Claude 3.5 or 3.7 model.")

        # Check in configured models first
        for m in self.configured_models:
            if str(m.get("id") or "").lower() == clean_lower:
                return self._parse_model_item(m)

        # Check default models
        for item in DEFAULT_ANTHROPIC_MODELS:
            if item["id"].lower() == clean_lower:
                return self._parse_model_item(item)

        # Query live API
        try:
            with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
                resp = client.get(f"{self.base_url}/models?limit=100", headers=self._headers())
                if resp.is_success:
                    payload = resp.json()
                    for item in payload.get("data") or []:
                        if str(item.get("id") or "").lower() == clean_lower:
                            return self._parse_model_item(item)
        except Exception:
            pass

        # If it matches a standard Claude identifier pattern, accept it with default Claude specs
        if clean_lower.startswith("claude-"):
            return self._parse_model_item({"id": clean_id, "display_name": clean_id})

        raise LookupError(f"Model '{clean_id}' not found in Anthropic catalog.")

    def stream(
        self,
        model_id: str,
        system_instruction: str,
        history: list[dict[str, str]],
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Callable[[str, dict[str, Any]], tuple[dict[str, Any], int]] | None = None,
    ) -> Iterator[StreamEvent]:
        """Stream completion events with Anthropic Messages API multi-turn tool calling."""
        # Build Anthropic-compatible message history (alternating user/assistant)
        anthropic_messages: list[dict[str, Any]] = []
        for item in history:
            role = "user" if item.get("role") == "user" else "assistant"
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if anthropic_messages and anthropic_messages[-1]["role"] == role:
                anthropic_messages[-1]["content"] += f"\n\n{content}"
            else:
                anthropic_messages.append({"role": role, "content": content})

        # Append current user prompt
        if anthropic_messages and anthropic_messages[-1]["role"] == "user":
            anthropic_messages[-1]["content"] += f"\n\n{prompt}"
        else:
            anthropic_messages.append({"role": "user", "content": prompt})

        # Ensure first message is user
        if anthropic_messages and anthropic_messages[0]["role"] != "user":
            anthropic_messages.insert(0, {"role": "user", "content": "Hello"})

        # Format tools for Anthropic (input_schema)
        anthropic_tools: list[dict[str, Any]] = []
        if tools:
            for t in tools:
                if "function" in t:
                    fn = t["function"]
                    anthropic_tools.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object"}),
                    })
                elif "input_schema" in t:
                    anthropic_tools.append(t)
                elif "parameters" in t:
                    anthropic_tools.append({
                        "name": t.get("name"),
                        "description": t.get("description", ""),
                        "input_schema": t.get("parameters", {"type": "object"}),
                    })

        # Determine max tokens for model
        lower_id = model_id.lower()
        if "3-7" in lower_id or "3.7" in lower_id or "3-5" in lower_id or "3.5" in lower_id:
            max_tokens = 8192
        else:
            max_tokens = 4096

        url = f"{self.base_url}/messages"
        logger.debug(
            "Anthropic Claude stream starting: model=%s history_messages=%d tools_provided=%d",
            model_id,
            len(history),
            len(anthropic_tools),
        )

        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 64
                any_text_streamed = False
                seen_tool_signatures: list[str] = []
                total_input_tokens: int | None = None
                total_output_tokens: int = 0

                for turn_idx in range(max_turns):
                    body: dict[str, Any] = {
                        "model": model_id,
                        "max_tokens": max_tokens,
                        "system": system_instruction,
                        "messages": anthropic_messages,
                        "stream": True,
                    }
                    if anthropic_tools and turn_idx < (max_turns - 1):
                        body["tools"] = anthropic_tools
                    elif anthropic_tools:
                        body["tool_choice"] = {"type": "none"}

                    accumulated_content = ""
                    accumulated_tool_calls: dict[int, dict[str, Any]] = {}
                    current_event_type = ""

                    with client.stream("POST", url, headers=self._headers(), json=body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line:
                                continue
                            if line.startswith("event:"):
                                current_event_type = line[6:].strip()
                                continue
                            if not line.startswith("data:"):
                                continue

                            data_str = line[5:].strip()
                            if not data_str or data_str == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            event_type = chunk.get("type") or current_event_type

                            if event_type == "message_start":
                                msg = chunk.get("message") or {}
                                usage = msg.get("usage") or {}
                                if usage.get("input_tokens") is not None:
                                    total_input_tokens = (total_input_tokens or 0) + int(usage["input_tokens"])

                            elif event_type == "content_block_start":
                                idx = chunk.get("index", 0)
                                block = chunk.get("content_block") or {}
                                if block.get("type") == "tool_use":
                                    accumulated_tool_calls[idx] = {
                                        "id": block.get("id", f"toolu_{idx}"),
                                        "name": block.get("name", ""),
                                        "input_json": "",
                                    }

                            elif event_type == "content_block_delta":
                                idx = chunk.get("index", 0)
                                delta = chunk.get("delta") or {}
                                d_type = delta.get("type")
                                if d_type == "text_delta":
                                    text_piece = delta.get("text") or ""
                                    accumulated_content += text_piece
                                    yield StreamEvent("text_delta", text=text_piece)
                                    any_text_streamed = True
                                elif d_type == "input_json_delta":
                                    partial = delta.get("partial_json") or ""
                                    if idx not in accumulated_tool_calls:
                                        accumulated_tool_calls[idx] = {
                                            "id": f"toolu_{idx}",
                                            "name": "",
                                            "input_json": "",
                                        }
                                    accumulated_tool_calls[idx]["input_json"] += partial

                            elif event_type == "message_delta":
                                usage = chunk.get("usage") or {}
                                if usage.get("output_tokens") is not None:
                                    total_output_tokens += int(usage["output_tokens"])

                            elif event_type == "error":
                                err = chunk.get("error") or {}
                                raise ChatProviderResponseError(
                                    err.get("message") or "Anthropic streaming error"
                                )

                    # Check if model requested tool execution
                    if accumulated_tool_calls and tool_executor is not None and turn_idx < (max_turns - 1):
                        assistant_blocks: list[dict[str, Any]] = []
                        if accumulated_content:
                            assistant_blocks.append({"type": "text", "text": accumulated_content})

                        user_tool_results: list[dict[str, Any]] = []

                        for _, call_info in sorted(accumulated_tool_calls.items()):
                            fn_name = call_info["name"]
                            raw_input = call_info["input_json"]
                            try:
                                fn_args = json.loads(raw_input) if raw_input else {}
                            except json.JSONDecodeError:
                                fn_args = {}

                            call_id = call_info["id"]
                            assistant_blocks.append({
                                "type": "tool_use",
                                "id": call_id,
                                "name": fn_name,
                                "input": fn_args,
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
                            user_tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": call_id,
                                "content": json.dumps(result_data, default=str),
                            })

                        anthropic_messages.append({
                            "role": "assistant",
                            "content": assistant_blocks,
                        })
                        anthropic_messages.append({
                            "role": "user",
                            "content": user_tool_results,
                        })
                        logger.info(
                            "Anthropic Claude turn %d executed %d tool calls; looping",
                            turn_idx + 1,
                            len(user_tool_results),
                        )
                        continue

                    # Final turn or no tool calls
                    if total_input_tokens is not None or total_output_tokens:
                        yield StreamEvent(
                            "usage",
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens or None,
                        )
                    logger.info(
                        "Anthropic Claude stream finished: model=%s turns=%d text_len=%d",
                        model_id,
                        turn_idx + 1,
                        len(accumulated_content),
                    )
                    break

                # Safety fallback: if no text streamed across all turns, issue a forced synthesis request
                if not any_text_streamed:
                    fallback_body = {
                        "model": model_id,
                        "max_tokens": 1024,
                        "system": system_instruction,
                        "messages": anthropic_messages,
                        "stream": True,
                    }
                    with client.stream("POST", url, headers=self._headers(), json=fallback_body) as fb_resp:
                        if fb_resp.is_success:
                            for fb_line in fb_resp.iter_lines():
                                if not fb_line or not fb_line.startswith("data:"):
                                    continue
                                fb_data = fb_line[5:].strip()
                                if not fb_data or fb_data == "[DONE]":
                                    break
                                try:
                                    fb_chunk = json.loads(fb_data)
                                except json.JSONDecodeError:
                                    continue
                                if fb_chunk.get("type") == "content_block_delta":
                                    fb_delta = fb_chunk.get("delta") or {}
                                    if fb_delta.get("type") == "text_delta":
                                        fb_text = fb_delta.get("text") or ""
                                        yield StreamEvent("text_delta", text=fb_text)

        except httpx.TimeoutException as exc:
            logger.warning("Anthropic stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning("Anthropic stream network error: model=%s error=%s", model_id, exc)
            raise ChatProviderUnavailableError() from exc

