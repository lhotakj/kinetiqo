"""Validated provider-neutral chat domain records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Role = Literal["user", "assistant"]
MessageStatus = Literal["complete", "failed", "interrupted"]


@dataclass(frozen=True)
class ChatProviderModel:
    id: str
    display_name: str
    supports_vision: bool = False
    supports_tools: bool = False
    context_length: int | None = None
    max_output_tokens: int | None = None
    pricing: dict[str, Any] | None = None
    rate_limits: dict[str, Any] | None = None
    request_limits: dict[str, Any] | None = None
    description: str | None = None


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    session_id: str
    athlete_id: str
    role: Role
    content: str
    seq: int
    status: MessageStatus
    created_at: datetime
    provider: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_provenance: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    athlete_id: str
    title: str
    provider: str
    model_id: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True)
class StreamEvent:
    type: Literal["text_delta", "usage", "completed", "tool_call", "tool_result"]
    text: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    tool_data: dict[str, Any] | None = None

