"""Minimal official Gemini REST adapter using httpx and SSE."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import httpx

from kinetiqo.chat.errors import ChatAuthenticationError, ChatProviderResponseError, ChatProviderUnavailableError, ChatRateLimitError, ChatSafetyBlockedError, ChatTimeoutError
from kinetiqo.chat.models import ChatProviderModel, StreamEvent
from kinetiqo.chat.providers.base import BaseChatProvider

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
logger = logging.getLogger("kinetiqo.chat.gemini")

DEPRECATED_MODELS = frozenset({
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-flash-image",
})

EXCLUDED_MODEL_PATTERNS = (
    "-tts",
    "-image",
    "imagen",
    "embedding",
    "aqa",
    "bison",
    "gecko",
)

PREFERRED_MODELS = (
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
)


class GeminiChatProvider(BaseChatProvider):
    provider_name = "gemini"
    default_model = "gemini-3.1-flash-lite"
    deprecated_models = DEPRECATED_MODELS
    preferred_models = PREFERRED_MODELS

    def __init__(self, api_key: str, client_factory=httpx.Client):
        super().__init__(api_key, client_factory or httpx.Client)

    def list_models(self) -> list[ChatProviderModel]:
        payload = self._request_json("GET", f"{_BASE_URL}/models")
        result = []
        for model in payload.get("models", []):
            methods = model.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
            name = model.get("name", "").removeprefix("models/")
            if not name:
                continue
            lower_name = name.lower()
            if lower_name in DEPRECATED_MODELS:
                continue
            if any(pattern in lower_name for pattern in EXCLUDED_MODEL_PATTERNS):
                continue
            result.append(ChatProviderModel(name, model.get("displayName") or name, "generateContent" in methods, "generateContent" in methods))

        def model_rank(m: ChatProviderModel) -> int:
            for idx, pref in enumerate(PREFERRED_MODELS):
                if m.id == pref:
                    return idx
            return len(PREFERRED_MODELS) + 1

        result.sort(key=lambda m: (model_rank(m), m.id))
        logger.info("Gemini model discovery completed: available_models=%d", len(result))
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
        contents: list[dict[str, Any]] = [{"role": "user" if item["role"] == "user" else "model", "parts": [{"text": item["content"]}]} for item in history]
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        url = f"{_BASE_URL}/models/{model_id}:streamGenerateContent?alt=sse"
        logger.debug("Gemini stream starting: model=%s history_messages=%d tools_provided=%d", model_id, len(history), len(tools or []))
        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 16  # allow multi-year comparisons up to 15 tool rounds + final answer
                any_text_streamed = False
                for turn_idx in range(max_turns):
                    body: dict[str, Any] = {
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "contents": contents,
                    }
                    # Omit tools on the final turn to force Gemini to synthesize the final answer
                    if tools and turn_idx < (max_turns - 1):
                        body["tools"] = [{"functionDeclarations": tools}]

                    turn_function_calls: list[dict[str, Any]] = []
                    turn_text_chunks: list[str] = []
                    turn_model_parts: list[dict[str, Any]] = []
                    last_usage: dict[str, Any] | None = None
                    event_count = 0

                    with client.stream("POST", url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            event_count += 1
                            try:
                                data = json.loads(line[5:].strip())
                            except json.JSONDecodeError as exc:
                                logger.warning("Gemini stream contained invalid SSE JSON: model=%s event_index=%d", model_id, event_count)
                                raise ChatProviderResponseError() from exc
                            feedback = data.get("promptFeedback", {})
                            if feedback.get("blockReason"):
                                raise ChatSafetyBlockedError()
                            candidates = data.get("candidates", [])
                            for candidate in candidates:
                                if candidate.get("finishReason") in {"SAFETY", "RECITATION"}:
                                    raise ChatSafetyBlockedError()
                                candidate_parts = candidate.get("content", {}).get("parts", [])
                                for part in candidate_parts:
                                    if "functionCall" in part:
                                        turn_function_calls.append(part["functionCall"])
                                        turn_model_parts.append(part)
                                    elif "text" in part and isinstance(part["text"], str):
                                        text_str = part["text"]
                                        turn_text_chunks.append(text_str)
                                        turn_model_parts.append(part)
                            usage = data.get("usageMetadata", {})
                            if usage:
                                last_usage = usage

                    # If model invoked one or more tools, execute them and continue to next turn
                    if turn_function_calls and tool_executor is not None and turn_idx < (max_turns - 1):
                        executed_results: list[tuple[str, Any]] = []
                        for call in turn_function_calls:
                            fn_name = call.get("name", "")
                            fn_args = call.get("args") or {}
                            yield StreamEvent("tool_call", tool=fn_name, arguments=fn_args)
                            result_data, _ = tool_executor(fn_name, fn_args)
                            executed_results.append((fn_name, result_data))
                            yield StreamEvent("tool_result", tool=fn_name, tool_data=result_data)

                        contents.append({"role": "model", "parts": turn_model_parts})
                        contents.append({
                            "role": "function",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": fn_name,
                                        "response": res if isinstance(res, dict) else {"result": res},
                                    }
                                }
                                for fn_name, res in executed_results
                            ],
                        })
                        logger.info("Gemini turn %d executed %d tool calls; looping", turn_idx + 1, len(executed_results))
                        continue

                    # No function calls or final turn; this is the answer turn. Stream text deltas.
                    for chunk in turn_text_chunks:
                        if chunk:
                            yield StreamEvent("text_delta", text=chunk)
                            any_text_streamed = True
                    if last_usage:
                        yield StreamEvent("usage", input_tokens=last_usage.get("promptTokenCount"), output_tokens=last_usage.get("candidatesTokenCount"))
                    logger.info("Gemini stream completed: model=%s turns=%d text_events=%d", model_id, turn_idx + 1, len(turn_text_chunks))
                    break

                # Safety fallback: if no text deltas were streamed after tool looping, perform synthesis call without tools
                if not any_text_streamed:
                    logger.info("Performing final Gemini synthesis pass without tools: model=%s", model_id)
                    synth_body = {
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "contents": contents,
                    }
                    with client.stream("POST", url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=synth_body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            try:
                                data = json.loads(line[5:].strip())
                            except Exception:
                                continue
                            for candidate in data.get("candidates", []):
                                for part in candidate.get("content", {}).get("parts", []):
                                    if "text" in part and isinstance(part["text"], str) and part["text"]:
                                        yield StreamEvent("text_delta", text=part["text"])
                                        any_text_streamed = True

            yield StreamEvent("completed")
        except (ChatAuthenticationError, ChatProviderResponseError, ChatProviderUnavailableError, ChatRateLimitError, ChatSafetyBlockedError):
            logger.warning("Gemini stream failed: model=%s category=%s", model_id, "provider_response")
            raise
        except httpx.TimeoutException as exc:
            logger.warning("Gemini stream timed out: model=%s", model_id)
            raise ChatTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning("Gemini stream transport failure: model=%s exception=%s", model_id, type(exc).__name__)
            raise ChatProviderUnavailableError() from exc

    def _request_json(self, method: str, url: str) -> dict[str, Any]:
        try:
            with self.client_factory(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                response = client.request(method, url, headers={"x-goog-api-key": self.api_key})
                self._raise_for_status(response)
                return response.json()
        except httpx.TimeoutException as exc:
            logger.warning("Gemini model discovery timed out")
            raise ChatTimeoutError() from exc
        except httpx.HTTPError as exc:
            logger.warning("Gemini model discovery transport failure: exception=%s", type(exc).__name__)
            raise ChatProviderUnavailableError() from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        provider_status = "unknown"
        try:
            # httpx deliberately leaves a streamed response unread.  Consume it
            # only on failure so json() can extract the provider's status code;
            # the payload itself is never logged or returned to the browser.
            response.read()
            payload = response.json()
            provider_status = str(payload.get("error", {}).get("status", "unknown"))[:64]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        request_id = response.headers.get("x-request-id") or response.headers.get("x-goog-request-id") or "unavailable"
        logger.warning(
            "Gemini API rejected request: http_status=%d provider_status=%s request_id=%s",
            response.status_code,
            provider_status,
            request_id[:128],
        )
        if response.status_code in (401, 403):
            raise ChatAuthenticationError()
        if response.status_code == 429:
            raise ChatRateLimitError()
        if response.status_code >= 500:
            raise ChatProviderUnavailableError()
        if response.status_code >= 400:
            raise ChatProviderResponseError()

