"""Ollama REST adapter using httpx and OpenAI-compatible streaming SSE."""

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

logger = logging.getLogger("kinetiqo.chat.ollama")

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct"


class OllamaChatProvider(BaseChatProvider):
    provider_name = "ollama"
    default_model = DEFAULT_OLLAMA_MODEL

    def __init__(
        self,
        api_key: str = "",
        client_factory=httpx.Client,
        config: dict[str, Any] | None = None,
        base_url: str | None = None,
    ):
        super().__init__(api_key, client_factory or httpx.Client)
        self.config = config or {}
        raw_url = base_url or self.config.get("base_url") or DEFAULT_OLLAMA_BASE_URL
        self.base_url = str(raw_url).strip().rstrip("/")
        self.configured_models = self.config.get("models") or []

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def list_models(self) -> list[ChatProviderModel]:
        """Fetch models dynamically from Ollama server (/api/tags or /v1/models)."""
        # Try native /api/tags first (contains rich details like parameter_size)
        try:
            with self.client_factory(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                resp = client.get(f"{self.base_url}/api/tags", headers=self._headers())
                if resp.is_success:
                    data = resp.json()
                    models = data.get("models", [])
                    result: list[ChatProviderModel] = []
                    for m in models:
                        mid = m.get("name") or m.get("model", "")
                        if not mid:
                            continue
                        details = m.get("details", {})
                        param_size = details.get("parameter_size", "")
                        disp_name = f"{mid} ({param_size})" if param_size else mid
                        result.append(ChatProviderModel(
                            id=mid,
                            display_name=disp_name,
                            supports_tools=True,
                        ))
                    if result:
                        logger.info("Discovered %d models from Ollama (/api/tags)", len(result))
                        return result
        except Exception as exc:
            logger.debug("Ollama /api/tags discovery failed: %s; trying /v1/models", exc)

        # Fallback to OpenAI-compatible /v1/models
        try:
            with self.client_factory(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                resp = client.get(f"{self.base_url}/v1/models", headers=self._headers())
                if resp.is_success:
                    data = resp.json()
                    m_list = data.get("data", [])
                    result = []
                    for m in m_list:
                        mid = m.get("id", "")
                        if mid:
                            result.append(ChatProviderModel(
                                id=mid,
                                display_name=mid,
                                supports_tools=True,
                            ))
                    if result:
                        logger.info("Discovered %d models from Ollama (/v1/models)", len(result))
                        return result
        except Exception as exc:
            logger.warning("Ollama model discovery failed: %s", exc)

        # Fallback to configured models in database if server is temporarily unreachable
        if self.configured_models:
            return [
                ChatProviderModel(
                    id=m.get("id", ""),
                    display_name=m.get("name") or m.get("id", ""),
                    supports_tools=True,
                )
                for m in self.configured_models
                if m.get("id")
            ]

        return [ChatProviderModel(
            id=DEFAULT_OLLAMA_MODEL,
            display_name=DEFAULT_OLLAMA_MODEL,
            supports_tools=True,
        )]

    @classmethod
    def test_connection(cls, base_url: str, api_key: str = "", client_factory=httpx.Client) -> dict[str, Any]:
        """Test reachability of an Ollama server and enumerate pulled models."""
        url = str(base_url).strip().rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key and api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        with client_factory(timeout=httpx.Timeout(6.0, connect=3.0)) as client:
            try:
                resp = client.get(f"{url}/api/tags", headers=headers)
                if not resp.is_success:
                    resp = client.get(f"{url}/v1/models", headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                raise ConnectionError(
                    f"Could not connect to Ollama at {url}. "
                    "Make sure Ollama is running and OLLAMA_HOST=0.0.0.0:11434 is set if connecting across your network."
                ) from exc
            except httpx.TimeoutException as exc:
                raise TimeoutError(f"Connection to Ollama at {url} timed out.") from exc

            if not resp.is_success:
                raise ValueError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            models = []
            if "models" in data:
                for m in data["models"]:
                    name = m.get("name") or m.get("model", "")
                    details = m.get("details", {})
                    param_size = details.get("parameter_size", "")
                    models.append({
                        "id": name,
                        "name": f"{name} ({param_size})" if param_size else name,
                        "parameter_size": param_size,
                    })
            elif "data" in data:
                for m in data["data"]:
                    mid = m.get("id", "")
                    if mid:
                        models.append({"id": mid, "name": mid})
            return {"connected": True, "base_url": url, "models": models}

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

        url = f"{self.base_url}/v1/chat/completions"
        logger.debug("Ollama stream starting: model=%s history_messages=%d tools_provided=%d", model_id, len(history), len(tools or []))

        try:
            with self.client_factory(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
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
                        logger.info("Ollama turn %d executed %d tool calls; looping", turn_idx + 1, len(assistant_tool_calls))
                        continue

                    if last_usage:
                        yield StreamEvent(
                            "usage",
                            input_tokens=last_usage.get("prompt_tokens"),
                            output_tokens=last_usage.get("completion_tokens"),
                        )
                    logger.info("Ollama stream completed: model=%s turns=%d content_len=%d", model_id, turn_idx + 1, len(accumulated_content))
                    break

                # Safety fallback
                if not any_text_streamed:
                    logger.info("Performing final Ollama synthesis pass without tools: model=%s", model_id)
                    fallback_body = {
                        "model": model_id,
                        "messages": messages,
                        "stream": True,
                    }
                    with client.stream("POST", url, headers=self._headers(), json=fallback_body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except Exception:
                                continue
                            delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                            text_piece = delta.get("content")
                            if text_piece:
                                yield StreamEvent("text_delta", text=text_piece)
                                any_text_streamed = True

            yield StreamEvent("completed")
        except (ChatAuthenticationError, ChatProviderResponseError, ChatProviderUnavailableError, ChatRateLimitError, ChatSafetyBlockedError):
            logger.warning("Ollama stream failed: model=%s category=%s", model_id, "provider_response")
            raise
        except httpx.TimeoutException as exc:
            logger.warning("Ollama stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning("Ollama stream transport failure: model=%s exception=%s", model_id, type(exc).__name__)
            raise ChatProviderUnavailableError() from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code in (401, 403):
            raise ChatAuthenticationError("Ollama rejected authentication token.")
        if response.status_code == 429:
            raise ChatRateLimitError("Ollama rate limit exceeded.")
        if response.status_code == 404:
            raise ChatProviderResponseError(f"Model or endpoint not found on Ollama server (HTTP {response.status_code}).")
        if response.status_code >= 500:
            raise ChatProviderUnavailableError("Ollama server error. Check Ollama process status.")
        raise ChatProviderResponseError(f"Ollama returned HTTP {response.status_code}.")
