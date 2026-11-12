"""PayPerQ (PPQ.AI) REST adapter using httpx and OpenAI-compatible streaming SSE."""

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


class PayPerQChatProvider(BaseChatProvider):
    provider_name = "payperq"
    display_name = "PayPerQ"
    description = "Subscription-free pay-per-query AI gateway to 100+ frontier & open models via PayPerQ (ppq.ai)"
    base_url = _BASE_URL
    default_model = "auto"
    preferred_models = tuple(m["id"] for m in DEFAULT_PAYPERQ_MODELS)
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
            "User-Agent": "Kinetiqo-Fitness-AI",
            "HTTP-Referer": "https://github.com/lhotakj/kinetiqo",
            "X-Title": "Kinetiqo",
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
                "PayPerQ rejected key: http_status=%d code=%s body=%s",
                response.status_code,
                err_code or "-",
                err_body[:500],
            )
            detail = f": {summary_detail}" if summary_detail else ". Check your API key at ppq.ai."
            raise ChatAuthenticationError(
                f"PayPerQ access rejected (HTTP {response.status_code}){detail}"
            )
        if response.status_code == 402:
            logger.warning("PayPerQ returned 402 (Payment Required): %s", err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"PayPerQ account has insufficient credits or unpaid invoice{detail}")
        if response.status_code == 429:
            logger.warning("PayPerQ rate limit hit: http_status=429 %s", err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(f"PayPerQ rate limit or concurrency quota exceeded{detail}")
        if 500 <= response.status_code < 600:
            logger.warning("PayPerQ upstream error: http_status=%d %s", response.status_code, err_body[:500])
            raise ChatProviderUnavailableError("PayPerQ is temporarily unavailable.")

        logger.warning("PayPerQ error response: http_status=%d body=%s", response.status_code, err_body[:500])
        detail = f": {summary_detail}" if summary_detail else "."
        raise ChatProviderResponseError(f"PayPerQ returned an error (HTTP {response.status_code}){detail}")

    def validate_credentials(self) -> None:
        """Validate PayPerQ credentials against models catalog endpoint."""
        with self.client_factory(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = client.get(f"{self.base_url}/models", headers=self._headers())
            self._raise_for_status(resp)

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate a PayPerQ model ID by fetching its metadata from PayPerQ Gateway."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        clean_lower = clean_id.lower()
        if "embed" in clean_lower:
            raise ValueError(
                f"'{clean_id}' is an embedding model, not a generative chat model. "
                "PayPerQ requires chat instruction models (such as auto, autoclaw/eco, or claude-sonnet-4.6) for AI Chat."
            )

        with self.client_factory(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
            # 1. Try single model endpoint directly (e.g. GET /models/{clean_id})
            single_url = f"{self.base_url}/models/{clean_id}"
            try:
                single_resp = client.get(single_url, headers=self._headers())
                if single_resp.status_code == 200:
                    item = single_resp.json()
                    if isinstance(item, dict) and item.get("id"):
                        parsed = self._parse_model_item(item)
                        if parsed.get("is_embedding"):
                            raise ValueError(
                                f"'{clean_id}' is an embedding model and cannot be used for text chat. Please choose a generative chat model."
                            )
                        return parsed
                elif single_resp.status_code in (401, 403):
                    self._raise_for_status(single_resp)
            except (ChatAuthenticationError, ValueError):
                raise
            except Exception as exc:
                logger.debug("PayPerQ direct model lookup failed (%s); falling back to catalog search: %s", single_url, exc)

            # 2. Fall back to catalog query for exact / fuzzy matching
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

            # 2a. Exact match (case-insensitive)
            for item in models:
                mid = (item.get("id") or "").lower()
                if mid == clean_lower:
                    parsed = self._parse_model_item(item)
                    if parsed.get("is_embedding"):
                        raise ValueError(
                            f"'{clean_id}' is an embedding model and cannot be used for text chat. Please choose a generative chat model."
                        )
                    return parsed

            # 2b. Candidate matching without provider prefix (e.g. 'claude-sonnet-4.6' -> 'anthropic/claude-sonnet-4.6')
            candidates: list[str] = []
            for item in models:
                raw_id = item.get("id") or ""
                mid = raw_id.lower()
                slug = mid.split("/", 1)[-1] if "/" in mid else mid
                if slug == clean_lower or clean_lower in mid or mid in clean_lower:
                    candidates.append(raw_id)

            if candidates:
                best_suggestion = candidates[0]
                err = LookupError(
                    f"Model '{clean_id}' was not found in PayPerQ. Did you mean '{best_suggestion}'?"
                )
                setattr(err, "suggestion", best_suggestion)
                raise err

        raise LookupError(f"Model '{clean_id}' was not found in PayPerQ.")

    @staticmethod
    def _parse_model_item(item: dict[str, Any]) -> dict[str, Any]:
        mid = item.get("id", "")
        name = item.get("name") or mid
        context_len = (
            item.get("context_window")
            or item.get("context_length")
            or item.get("max_tokens")
            or 128000
        )
        try:
            parsed_ctx = int(context_len) if context_len is not None else 128000
        except (ValueError, TypeError):
            parsed_ctx = 128000
        tags = item.get("tags") or []
        supported_params = item.get("supported_parameters") or []
        modalities = item.get("modalities") or {}
        input_mods = modalities.get("input") or [] if isinstance(modalities, dict) else []

        supports_vision = (
            "image" in input_mods
            or "vision" in tags
            or "multimodal" in tags
            or item.get("supports_vision") is True
            or (isinstance(item.get("capabilities"), dict) and item["capabilities"].get("image") is True)
        )
        is_embedding = (
            item.get("type") == "embedding"
            or "embed" in mid.lower()
        )
        supports_tools = (
            ("tools" in supported_params or "tool-use" in tags or not supported_params)
            and not is_embedding
        )
        if isinstance(item.get("capabilities"), dict) and "tools" in item["capabilities"]:
            supports_tools = bool(item["capabilities"]["tools"])

        pricing = item.get("pricing") or None
        description = item.get("description") or ""
        max_output_tokens = item.get("max_output_tokens") or item.get("max_tokens")
        if max_output_tokens is not None:
            try:
                max_output_tokens = int(max_output_tokens)
            except (ValueError, TypeError):
                max_output_tokens = None

        return {
            "id": mid,
            "name": name,
            "display_name": name,
            "context_length": parsed_ctx,
            "supports_tools": bool(supports_tools),
            "supports_vision": bool(supports_vision),
            "pricing": pricing,
            "description": description,
            "max_output_tokens": max_output_tokens,
            "rate_limits": item.get("rate_limits"),
            "request_limits": item.get("request_limits") or item.get("per_request_limits"),
            "is_embedding": bool(is_embedding),
        }

    def list_models(self) -> list[ChatProviderModel]:
        """Discover models directly from PayPerQ /v1/models endpoint."""
        url = f"{self.base_url}/models"
        raw_models: list[dict[str, Any]] = []
        try:
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
        except (httpx.TimeoutException, httpx.RequestError, ChatProviderUnavailableError) as exc:
            logger.warning("PayPerQ models endpoint unreachable; using curated fallback models: %s", exc)
            raw_models = list(DEFAULT_PAYPERQ_MODELS)
        except ChatAuthenticationError:
            raise

        if not raw_models:
            raw_models = list(DEFAULT_PAYPERQ_MODELS)

        result: list[ChatProviderModel] = []
        seen_ids: set[str] = set()

        for item in raw_models:
            parsed = self._parse_model_item(item)
            mid = parsed["id"]
            if not mid or mid.lower() in seen_ids:
                continue
            if parsed.get("is_embedding"):
                continue
            seen_ids.add(mid.lower())
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

        # Sort models: auto / autoclaw first, followed by claude, deepseek, gpt-4, gemini
        def _model_sort_key(m: ChatProviderModel) -> tuple[int, str]:
            low = m.id.lower()
            if low == "auto":
                return (0, low)
            if "autoclaw" in low or "eco" in low:
                return (1, low)
            if "claude" in low or "sonnet" in low:
                return (2, low)
            if "deepseek" in low:
                return (3, low)
            if "gpt-4" in low or "openai" in low:
                return (4, low)
            if "gemini" in low:
                return (5, low)
            return (6, low)

        result.sort(key=_model_sort_key)
        logger.info("PayPerQ model discovery completed: available_models=%d", len(result))
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
        """Stream completion events with OpenAI-compatible multi-turn tool calling via PayPerQ."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for item in history:
            role = item["role"]
            content = item["content"]
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url}/chat/completions"
        logger.debug("PayPerQ stream starting: model=%s history_messages=%d tools_provided=%d", model_id, len(history), len(tools or []))

        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 64
                seen_tool_signatures: list[str] = []

                # Check if this model supports tools
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
                        logger.info("PayPerQ turn %d executed %d tool calls; looping", turn_idx + 1, len(executed_tool_messages))
                        continue

                    # Final turn or no tools called
                    if last_usage:
                        yield StreamEvent(
                            "usage",
                            input_tokens=last_usage.get("prompt_tokens"),
                            output_tokens=last_usage.get("completion_tokens"),
                        )
                    logger.info("PayPerQ stream finished: model=%s turns=%d text_len=%d", model_id, turn_idx + 1, len(accumulated_content))
                    break

        except httpx.TimeoutException as exc:
            logger.warning("PayPerQ stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning("PayPerQ stream network error: model=%s error=%s", model_id, exc)
            raise ChatProviderUnavailableError() from exc

