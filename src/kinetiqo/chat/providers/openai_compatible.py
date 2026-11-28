"""OpenAI-compatible chat provider base class.

Provides a unified, robust implementation for REST API gateways that adhere to
the OpenAI chat completions specification (such as OpenRouter, Kilo AI, MagnetAPI,
PayPerQ, Vercel AI Gateway, and Mistral AI).
"""

from collections.abc import Iterator
import json
import logging
from typing import Any, Callable, Optional
import httpx

from kinetiqo.chat.errors import (
    ChatAuthenticationError,
    ChatProviderResponseError,
    ChatProviderUnavailableError,
    ChatRateLimitError,
)
from kinetiqo.chat.models import ChatProviderModel, StreamEvent
from kinetiqo.chat.providers.base import BaseChatProvider

logger = logging.getLogger("kinetiqo.chat.openai_compatible")


class OpenAICompatibleChatProvider(BaseChatProvider):
    """Abstract base provider for OpenAI-compatible HTTP/SSE chat completion gateways."""

    auth_endpoint: Optional[str] = None
    default_timeout: float = 120.0
    connect_timeout: float = 10.0
    fallback_models: tuple[dict[str, Any], ...] = ()

    def __init__(
        self,
        api_key: str,
        client_factory: Any = httpx.Client,
        configured_models: Optional[list[dict[str, Any]]] = None,
    ):
        super().__init__(api_key, client_factory or httpx.Client)
        self.configured_models = configured_models or []

    def _headers(self) -> dict[str, str]:
        """Base headers for OpenAI-compatible HTTP requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Kinetiqo-Fitness-AI",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Translate upstream HTTP error status codes into domain exceptions."""
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
                    if "detail" in payload:
                        detail_val = payload["detail"]
                        if isinstance(detail_val, str):
                            err_msg = detail_val
                        elif isinstance(detail_val, list) and detail_val:
                            err_msg = "; ".join(
                                str(x.get("msg", ""))
                                for x in detail_val
                                if isinstance(x, dict) and x.get("msg")
                            )
                    err_obj = payload.get("error")
                    if isinstance(err_obj, dict):
                        err_msg = err_msg or str(err_obj.get("message") or "")
                        err_code = str(err_obj.get("code") or err_obj.get("type") or "")
                    elif isinstance(err_obj, str):
                        err_msg = err_msg or err_obj
                    elif payload.get("message"):
                        err_msg = err_msg or str(payload["message"])
            except Exception:
                pass

        summary_detail = err_msg or err_code or (err_body[:200].strip() if err_body else "")
        provider_label = self.display_name or self.provider_name.capitalize()

        if response.status_code in (401, 403):
            logger.warning(
                "%s API rejected key: http_status=%d code=%s body=%s",
                provider_label,
                response.status_code,
                err_code or "-",
                err_body[:500],
            )
            detail = f": {summary_detail}" if summary_detail else f". Check your API key and account settings."
            raise ChatAuthenticationError(
                f"{provider_label} access rejected (HTTP {response.status_code}){detail}"
            )
        if response.status_code == 402:
            logger.warning("%s API returned 402 (Payment Required): %s", provider_label, err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(
                f"{provider_label} account has insufficient credits or unpaid invoice{detail}"
            )
        if response.status_code == 429:
            logger.warning("%s API rate limit hit: http_status=429 %s", provider_label, err_body[:500])
            detail = f": {summary_detail}" if summary_detail else "."
            raise ChatRateLimitError(
                f"{provider_label} rate limit or concurrency quota exceeded{detail}"
            )
        if 500 <= response.status_code < 600:
            logger.warning("%s upstream error: http_status=%d %s", provider_label, response.status_code, err_body[:500])
            raise ChatProviderUnavailableError(f"{provider_label} is temporarily unavailable.")

        logger.warning("%s error response: http_status=%d body=%s", provider_label, response.status_code, err_body[:500])
        detail = f": {summary_detail}" if summary_detail else "."
        raise ChatProviderResponseError(
            f"{provider_label} returned an error (HTTP {response.status_code}){detail}"
        )

    def validate_credentials(self) -> None:
        """Validate credentials against upstream authentication or models endpoint."""
        url = self.auth_endpoint or f"{self.base_url}/models"
        with self.client_factory(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            resp = client.get(url, headers=self._headers())
            self._raise_for_status(resp)

    def _parse_model_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Extract normalized model attributes from an upstream catalog item."""
        mid = str(item.get("id") or "").strip()
        name = str(item.get("name") or mid).strip()

        # Context length detection
        ctx = item.get("context_length") or item.get("context_window") or item.get("max_context_length")
        if not ctx:
            for k in ("max_position_embeddings", "max_tokens", "max_input_tokens"):
                if item.get(k):
                    ctx = item[k]
                    break
        try:
            context_length = int(ctx) if ctx else 128000
        except (ValueError, TypeError):
            context_length = 128000

        # Modality & capabilities
        mid_lower = mid.lower()
        arch = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
        modality = arch.get("modality", "") if isinstance(arch, dict) else ""
        instruct_type = arch.get("instruct_type", "") if isinstance(arch, dict) else ""
        modalities = item.get("modalities") or {}
        input_mods = modalities.get("input") or [] if isinstance(modalities, dict) else []
        tags = item.get("tags") or []
        supported_params = item.get("supported_parameters") or []

        is_embedding = (
            item.get("type") == "embedding"
            or "embed" in mid_lower
            or "text-embedding" in mid_lower
            or "bge-" in mid_lower
            or modality == "text->embedding"
        )
        supports_vision = (
            bool(item.get("supports_vision"))
            or "vision" in mid_lower
            or "vision" in tags
            or "image" in input_mods
            or "multimodal" in tags
            or "vl" in mid_lower
            or "multimodal" in str(modality).lower()
            or "image" in str(modality).lower()
            or (isinstance(item.get("capabilities"), dict) and item["capabilities"].get("image") is True)
        )

        supports_tools = True
        if item.get("supports_tools") is not None:
            supports_tools = bool(item["supports_tools"])
        elif isinstance(item.get("capabilities"), dict) and "tools" in item["capabilities"]:
            supports_tools = bool(item["capabilities"]["tools"])
        elif supported_params:
            supports_tools = ("tools" in supported_params or "tool-use" in tags) and not is_embedding
        elif instruct_type == "none" or is_embedding:
            supports_tools = False

        res: dict[str, Any] = {
            "id": mid,
            "name": name,
            "display_name": name,
            "context_length": context_length,
            "supports_tools": supports_tools,
            "supports_vision": supports_vision,
            "is_embedding": is_embedding,
            "pricing": item.get("pricing") or {},
            "description": item.get("description") or "",
            "max_output_tokens": item.get("max_output_tokens") or item.get("max_tokens"),
            "rate_limits": item.get("rate_limits"),
            "request_limits": item.get("request_limits") or item.get("per_request_limits"),
        }
        return res

    def validate_model(self, model_id: str) -> dict[str, Any]:
        """Validate a model ID by testing against direct and catalog endpoints."""
        clean_id = model_id.strip()
        if not clean_id:
            raise ValueError("Model ID cannot be empty.")

        clean_lower = clean_id.lower()
        if "embed" in clean_lower:
            raise ValueError(
                f"'{clean_id}' is an embedding model and cannot be used for text chat. Please choose a generative chat model."
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
                logger.debug(
                    "%s direct model lookup failed (%s); falling back to catalog search: %s",
                    self.display_name,
                    single_url,
                    exc,
                )

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

            # 2b. Candidate matching without provider prefix (e.g. 'llama-3.3-70b-instruct' -> 'meta-llama/llama-3.3-70b-instruct')
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
                    f"Model '{clean_id}' was not found in {self.display_name}. Did you mean '{best_suggestion}'?"
                )
                setattr(err, "suggestion", best_suggestion)
                raise err

            raise LookupError(
                f"Model '{clean_id}' was not found in {self.display_name}."
            )

    def list_models(self) -> list[ChatProviderModel]:
        """List operational models for this provider."""
        if self.configured_models:
            models: list[ChatProviderModel] = []
            for m in self.configured_models:
                mid = m.get("id", "")
                if not mid:
                    continue
                models.append(
                    ChatProviderModel(
                        id=mid,
                        display_name=m.get("display_name") or m.get("name", mid),
                        context_length=m.get("context_length", 128000),
                        supports_tools=m.get("supports_tools", True),
                        supports_vision=m.get("supports_vision", False),
                    )
                )
            return models

        # When discovered mode, query the catalog endpoint
        if self.model_mode == "discovered":
            try:
                with self.client_factory(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
                    resp = client.get(f"{self.base_url}/models", headers=self._headers())
                    self._raise_for_status(resp)
                    payload = resp.json()
                    raw_list = payload.get("data") if isinstance(payload, dict) else payload
                    if isinstance(raw_list, list):
                        res = []
                        for item in raw_list:
                            p = self._parse_model_item(item)
                            if p.get("is_embedding"):
                                continue
                            if p["id"] in self.deprecated_models:
                                continue
                            res.append(
                                ChatProviderModel(
                                    id=p["id"],
                                    display_name=p["display_name"],
                                    context_length=p["context_length"],
                                    supports_tools=p["supports_tools"],
                                    supports_vision=p["supports_vision"],
                                )
                            )
                        if res:
                            return sorted(
                                res,
                                key=lambda m: (
                                    0 if m.id in self.preferred_models else 1,
                                    self.preferred_models.index(m.id) if m.id in self.preferred_models else 999,
                                    m.id,
                                ),
                            )
            except ChatAuthenticationError:
                raise
            except Exception as e:
                logger.warning("%s list_models query failed: %s", self.display_name, e)

        # Fallback models
        source_fallbacks = self.fallback_models or self.suggested_models
        return [
            ChatProviderModel(
                id=m["id"] if isinstance(m, dict) else m.id,
                display_name=m.get("label", m.get("name", m["id"])) if isinstance(m, dict) else m.display_name,
                context_length=m.get("context_length", 128000) if isinstance(m, dict) else m.context_length,
                supports_tools=m.get("supports_tools", True) if isinstance(m, dict) else m.supports_tools,
                supports_vision=m.get("supports_vision", False) if isinstance(m, dict) else m.supports_vision,
            )
            for m in source_fallbacks
        ]

    def stream(
        self,
        model_id: str,
        system_instruction: str,
        history: list[dict[str, str]],
        prompt: str,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_executor: Optional[Callable[[str, dict[str, Any]], tuple[dict[str, Any], int]]] = None,
    ) -> Iterator[StreamEvent]:
        """Stream completion events with OpenAI-compatible multi-turn tool calling."""
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        for item in history:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url}/chat/completions"
        logger.debug(
            "%s stream starting: model=%s history_messages=%d tools_provided=%d",
            self.display_name,
            model_id,
            len(history),
            len(tools or []),
        )

        try:
            with self.client_factory(timeout=httpx.Timeout(self.default_timeout, connect=self.connect_timeout)) as client:
                max_turns = 64
                seen_tool_signatures: list[str] = []

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
                    last_usage: Optional[dict[str, Any]] = None

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
                        if accumulated_content and not accumulated_content.endswith("\n\n"):
                            accumulated_content += "\n\n"
                            yield StreamEvent("text_delta", text="\n\n")

                        executed_tool_messages: list[dict[str, Any]] = []
                        assistant_tool_calls: list[dict[str, Any]] = []

                        for _, tc_data in sorted(accumulated_tool_calls.items(), key=lambda x: x[0]):
                            tool_name = tc_data["name"].strip()
                            call_id = tc_data["id"]
                            raw_args = tc_data["arguments"].strip()

                            parsed_args = {}
                            if raw_args:
                                try:
                                    parsed_args = json.loads(raw_args)
                                except json.JSONDecodeError:
                                    parsed_args = {"raw_input": raw_args}

                            sig = f"{tool_name}:{json.dumps(parsed_args, sort_keys=True, default=str)}"
                            seen_tool_signatures.append(sig)
                            yield StreamEvent("tool_call", tool=tool_name, arguments=parsed_args)

                            result, _ = tool_executor(tool_name, parsed_args)
                            if seen_tool_signatures.count(sig) >= 3 and isinstance(result, dict):
                                result["_directive"] = "You have queried this identical data multiple times. Do not call this tool again with identical parameters; synthesize your answer now."

                            yield StreamEvent("tool_result", tool=tool_name, tool_data=result)
                            assistant_tool_calls.append({
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": raw_args or "{}"},
                            })
                            executed_tool_messages.append({
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": tool_name,
                                "content": json.dumps(result, default=str),
                            })

                        messages.append({
                            "role": "assistant",
                            "content": accumulated_content or None,
                            "tool_calls": assistant_tool_calls,
                        })
                        messages.extend(executed_tool_messages)
                        continue

                    # Final turn or no tools called
                    if last_usage:
                        yield StreamEvent(
                            "usage",
                            input_tokens=last_usage.get("prompt_tokens"),
                            output_tokens=last_usage.get("completion_tokens"),
                        )
                    break
        except httpx.TimeoutException as e:
            logger.warning("%s stream timeout: %s", self.display_name, e)
            from kinetiqo.chat.errors import ChatTimeoutError
            raise ChatTimeoutError(f"Request to {self.display_name} timed out: {e}") from e
        except (httpx.RequestError, httpx.NetworkError) as e:
            logger.warning("%s stream connection error: %s", self.display_name, e)
            raise ChatProviderUnavailableError(f"{self.display_name} is unavailable: {e}") from e
        except (
            ChatAuthenticationError,
            ChatRateLimitError,
            ChatProviderUnavailableError,
            ChatProviderResponseError,
        ):
            raise
        except Exception as e:
            logger.warning("%s stream error: %s", self.display_name, e)
            raise ChatProviderResponseError(f"{self.display_name} streaming error: {e}") from e
