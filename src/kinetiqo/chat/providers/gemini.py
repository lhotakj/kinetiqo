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
        stream_ready = []
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
            entry = ChatProviderModel(
                id=name,
                display_name=model.get("displayName") or name,
                supports_vision="generateContent" in methods,
                supports_tools="generateContent" in methods,
                context_length=model.get("inputTokenLimit"),
                max_output_tokens=model.get("outputTokenLimit"),
                description=model.get("description"),
            )
            result.append(entry)
            if "streamGenerateContent" in methods:
                stream_ready.append(entry)

        def model_rank(m: ChatProviderModel) -> int:
            for idx, pref in enumerate(PREFERRED_MODELS):
                if m.id == pref:
                    return idx
            return len(PREFERRED_MODELS) + 1

        final_models = stream_ready if stream_ready else result
        final_models.sort(key=lambda m: (model_rank(m), m.id))
        logger.info("Gemini model discovery completed: available_models=%d", len(final_models))
        return final_models

    def stream(
        self,
        model_id: str,
        system_instruction: str,
        history: list[dict[str, str]],
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any = None,
    ) -> Iterator[StreamEvent]:
        contents: list[dict[str, Any]] = []
        for item in history:
            role = "user" if item["role"] == "user" else "model"
            text = item.get("content", "").strip()
            if not text:
                continue
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].append({"text": text})
            else:
                contents.append({"role": role, "parts": [{"text": text}]})

        if contents and contents[-1]["role"] == "user":
            contents[-1]["parts"].append({"text": prompt})
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        url = f"{_BASE_URL}/models/{model_id}:streamGenerateContent?alt=sse"
        logger.debug("Gemini stream starting: model=%s history_messages=%d tools_provided=%d", model_id, len(history), len(tools or []))
        try:
            with self.client_factory(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                max_turns = 64  # Generous headroom for multi-year, multi-sport, or complex analytics comparisons
                any_text_streamed = False
                seen_tool_signatures: list[str] = []

                for turn_idx in range(max_turns):
                    body: dict[str, Any] = {
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "contents": contents,
                    }
                    if tools:
                        body["tools"] = [{"functionDeclarations": tools}]
                        # On the final turn, force the model to synthesize text instead of issuing another function call
                        if turn_idx >= (max_turns - 1):
                            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}

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
                                        p = dict(part)
                                        fn_call = dict(p["functionCall"])
                                        call_id = fn_call.get("id") or p.get("id")
                                        if call_id and "id" not in fn_call:
                                            fn_call["id"] = call_id
                                        p["functionCall"] = fn_call
                                        sig = p.get("thoughtSignature") or p.get("thought_signature")
                                        if sig:
                                            p["thoughtSignature"] = sig
                                            p["thought_signature"] = sig
                                        turn_function_calls.append(fn_call)
                                        turn_model_parts.append(p)
                                    elif "text" in part and isinstance(part["text"], str):
                                        text_str = part["text"]
                                        turn_text_chunks.append(text_str)
                                        turn_model_parts.append(dict(part))
                            usage = data.get("usageMetadata", {})
                            if usage:
                                last_usage = usage

                    # If model invoked one or more tools, execute them and continue to next turn
                    if turn_function_calls and tool_executor is not None and turn_idx < (max_turns - 1):
                        executed_results: list[tuple[str, Any, str | None]] = []
                        for call in turn_function_calls:
                            call_id = call.get("id")
                            fn_name = call.get("name", "")
                            fn_args = call.get("args") or {}
                            sig = f"{fn_name}:{json.dumps(fn_args, sort_keys=True, default=str)}"
                            seen_tool_signatures.append(sig)
                            yield StreamEvent("tool_call", tool=fn_name, arguments=fn_args)
                            result_data, _ = tool_executor(fn_name, fn_args)
                            # Guard against repetitive identical queries
                            if seen_tool_signatures.count(sig) >= 3 and isinstance(result_data, dict):
                                result_data["_directive"] = "You have queried this identical data multiple times. Do not call this tool again with identical parameters; synthesize your answer now."
                            executed_results.append((fn_name, result_data, call_id))
                            yield StreamEvent("tool_result", tool=fn_name, tool_data=result_data)

                        contents.append({"role": "model", "parts": turn_model_parts})

                        response_parts: list[dict[str, Any]] = []
                        for fn_name, res, call_id in executed_results:
                            resp_item: dict[str, Any] = {
                                "name": fn_name,
                                "response": res if isinstance(res, dict) else {"result": res},
                            }
                            if call_id:
                                resp_item["id"] = call_id
                            response_parts.append({"functionResponse": resp_item})

                        contents.append({
                            "role": "user",
                            "parts": response_parts,
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

                # Safety fallback: if no text deltas were streamed after tool looping, perform synthesis call with mode NONE
                if not any_text_streamed:
                    logger.info("Performing final Gemini synthesis pass: model=%s", model_id)
                    synth_body: dict[str, Any] = {
                        "systemInstruction": {"parts": [{"text": system_instruction}]},
                        "contents": contents,
                    }
                    if tools:
                        synth_body["tools"] = [{"functionDeclarations": tools}]
                        synth_body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
                    synth_usage = None
                    with client.stream("POST", url, headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"}, json=synth_body) as response:
                        self._raise_for_status(response)
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            try:
                                data = json.loads(line[5:].strip())
                            except Exception:
                                continue
                            if "usageMetadata" in data:
                                synth_usage = data["usageMetadata"]
                            for candidate in data.get("candidates", []):
                                for part in candidate.get("content", {}).get("parts", []):
                                    if "text" in part and isinstance(part["text"], str) and part["text"]:
                                        yield StreamEvent("text_delta", text=part["text"])
                                        any_text_streamed = True
                    if synth_usage:
                        yield StreamEvent("usage", input_tokens=synth_usage.get("promptTokenCount"), output_tokens=synth_usage.get("candidatesTokenCount"))

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
        provider_message = ""
        try:
            # httpx deliberately leaves a streamed response unread.  Consume it
            # only on failure so json() can extract the provider's status code;
            # the payload itself is never logged or returned to the browser.
            response.read()
            payload = response.json()
            error_obj = payload.get("error", {})
            provider_status = str(error_obj.get("status", "unknown"))[:64]
            provider_message = str(error_obj.get("message", "")).strip()
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        request_id = response.headers.get("x-request-id") or response.headers.get("x-goog-request-id") or "unavailable"
        logger.warning(
            "Gemini API rejected request: http_status=%d provider_status=%s request_id=%s",
            response.status_code,
            provider_status,
            request_id[:128],
        )
        if provider_message:
            logger.info("Gemini API rejected detail: status=%s message=%s", provider_status, provider_message[:512])
        if response.status_code in (401, 403):
            raise ChatAuthenticationError("The Gemini API key was rejected or has expired. Please verify your API key in Settings.")
        if response.status_code == 429:
            if "quota" in provider_message.lower() or "resource_exhausted" in provider_status.lower():
                raise ChatRateLimitError("Gemini API quota exceeded. You have reached your account or model limit in Google AI Studio. Please check your quota or billing.")
            raise ChatRateLimitError("Gemini API rate limit reached. Please wait a moment before sending another message.")
        if response.status_code >= 500:
            raise ChatProviderUnavailableError()
        if response.status_code >= 400:
            if "token" in provider_message.lower() or "context" in provider_message.lower():
                raise ChatProviderResponseError(f"Model token or context limit reached: {provider_message}")
            if provider_message:
                raise ChatProviderResponseError(f"Gemini API error ({provider_status}): {provider_message}")
            raise ChatProviderResponseError()

