"""Portable raw-SQL persistence for chat records.

The repository deliberately uses application-generated UUIDs so PostgreSQL,
MySQL, and Firebird share one persistence contract.
"""

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from kinetiqo.chat.models import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, repository: Any, dialect: str):
        self.source_repository = repository
        self.conn = repository.conn
        self.dialect = dialect
        self.placeholder = "?" if dialect == "firebird" else "%s"

    def _one(self, query: str, values: tuple) -> tuple | None:
        cur = self.conn.cursor()
        try:
            cur.execute(query, values)
            return cur.fetchone()
        finally:
            cur.close()

    def _all(self, query: str, values: tuple) -> list[tuple]:
        cur = self.conn.cursor()
        try:
            cur.execute(query, values)
            return cur.fetchall()
        finally:
            cur.close()

    def _execute(self, query: str, values: tuple) -> None:
        cur = self.conn.cursor()
        try:
            cur.execute(query, values)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create_session(self, athlete_id: str, provider: str, model_id: str) -> ChatSession:
        now = self._now()
        record = ChatSession(str(uuid4()), athlete_id, "New chat", provider, model_id, now, now, None)
        p = self.placeholder
        self._execute(
            f"INSERT INTO chat_sessions (session_id, athlete_id, title, provider, model_id, created_at, updated_at, last_message_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
            (record.session_id, athlete_id, record.title, provider, model_id, now, now, None),
        )
        return record

    def get_session(self, athlete_id: str, session_id: str) -> ChatSession | None:
        p = self.placeholder
        row = self._one(f"SELECT session_id, athlete_id, title, provider, model_id, created_at, updated_at, last_message_at FROM chat_sessions WHERE session_id = {p} AND athlete_id = {p}", (session_id, athlete_id))
        return self._session(row) if row else None

    def list_sessions(self, athlete_id: str) -> list[ChatSession]:
        p = self.placeholder
        rows = self._all(f"SELECT session_id, athlete_id, title, provider, model_id, created_at, updated_at, last_message_at FROM chat_sessions WHERE athlete_id = {p} ORDER BY last_message_at DESC, session_id DESC", (athlete_id,))
        return [self._session(row) for row in rows]

    def update_session(self, athlete_id: str, session_id: str, title: str | None = None, provider: str | None = None, model_id: str | None = None) -> None:
        existing = self.get_session(athlete_id, session_id)
        if not existing:
            raise LookupError("Conversation not found.")
        now = self._now()
        p = self.placeholder
        self._execute(f"UPDATE chat_sessions SET title = {p}, provider = {p}, model_id = {p}, updated_at = {p} WHERE session_id = {p} AND athlete_id = {p}", (title if title is not None else existing.title, provider or existing.provider, model_id or existing.model_id, now, session_id, athlete_id))

    def delete_session(self, athlete_id: str, session_id: str) -> None:
        p = self.placeholder
        cur = self.conn.cursor()
        try:
            cur.execute(f"DELETE FROM chat_messages WHERE session_id = {p} AND athlete_id = {p}", (session_id, athlete_id))
            cur.execute(f"DELETE FROM chat_sessions WHERE session_id = {p} AND athlete_id = {p}", (session_id, athlete_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def clear_history(self, athlete_id: str) -> None:
        p = self.placeholder
        cur = self.conn.cursor()
        try:
            cur.execute(f"DELETE FROM chat_messages WHERE athlete_id = {p}", (athlete_id,))
            cur.execute(f"DELETE FROM chat_sessions WHERE athlete_id = {p}", (athlete_id,))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def add_message(self, athlete_id: str, session_id: str, role: str, content: str, status: str = "complete", provider: str | None = None, model_id: str | None = None) -> ChatMessage:
        session = self.get_session(athlete_id, session_id)
        if not session:
            raise LookupError("Conversation not found.")
        p = self.placeholder
        row = self._one(f"SELECT COALESCE(MAX(seq), 0) FROM chat_messages WHERE session_id = {p} AND athlete_id = {p}", (session_id, athlete_id))
        seq = int(row[0]) + 1
        now = self._now()
        message = ChatMessage(str(uuid4()), session_id, athlete_id, role, content, seq, status, now, provider, model_id)
        cur = self.conn.cursor()
        try:
            cur.execute(f"INSERT INTO chat_messages (message_id, session_id, athlete_id, seq, role, content, status, provider, model_id, error_code, input_tokens, output_tokens, tool_provenance, created_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})", (message.message_id, session_id, athlete_id, seq, role, content, status, provider, model_id, None, None, None, None, now))
            cur.execute(f"UPDATE chat_sessions SET last_message_at = {p}, updated_at = {p} WHERE session_id = {p} AND athlete_id = {p}", (now, now, session_id, athlete_id))
            if role == "user" and seq == 1:
                title = " ".join(content.split())[:120] or "New chat"
                cur.execute(f"UPDATE chat_sessions SET title = {p} WHERE session_id = {p} AND athlete_id = {p}", (title, session_id, athlete_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()
        return message

    def update_message(
        self,
        athlete_id: str,
        message_id: str,
        content: str,
        status: str,
        error_code: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        tool_provenance: str | None = None,
    ) -> None:
        p = self.placeholder
        self._execute(
            f"UPDATE chat_messages SET content = {p}, status = {p}, error_code = {p}, input_tokens = {p}, output_tokens = {p}, tool_provenance = {p} WHERE message_id = {p} AND athlete_id = {p}",
            (content, status, error_code, input_tokens, output_tokens, tool_provenance, message_id, athlete_id),
        )

    def list_messages(self, athlete_id: str, session_id: str, limit: int = 100) -> list[ChatMessage]:
        p = self.placeholder
        rows = self._all(f"SELECT message_id, session_id, athlete_id, role, content, seq, status, created_at, provider, model_id, input_tokens, output_tokens, tool_provenance, error_code FROM chat_messages WHERE session_id = {p} AND athlete_id = {p} ORDER BY seq ASC", (session_id, athlete_id))
        return [self._message(row) for row in rows[-limit:]]

    def get_provider_key(self, athlete_id: str, provider: str) -> str | None:
        p = self.placeholder
        row = self._one(f"SELECT api_key_enc FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}", (athlete_id, provider))
        if not row or not row[0]:
            return None
        val = row[0]
        return val.read() if hasattr(val, "read") else str(val)

    def get_provider_config(self, athlete_id: str, provider: str) -> dict[str, Any]:
        p = self.placeholder
        row = self._one(f"SELECT config_json FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}", (athlete_id, provider))
        if not row or not row[0]:
            return {}
        val = row[0]
        raw = val.read() if hasattr(val, "read") else str(val)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def save_provider_config(self, athlete_id: str, provider: str, config: dict[str, Any]) -> None:
        p = self.placeholder
        now = self._now()
        raw_json = json.dumps(config)
        row = self._one(f"SELECT key_id FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}", (athlete_id, provider))
        if row:
            self._execute(
                f"UPDATE chat_provider_keys SET config_json = {p}, updated_at = {p} WHERE athlete_id = {p} AND provider = {p}",
                (raw_json, now, athlete_id, provider),
            )
        else:
            enabled_value = 1 if self.dialect == "firebird" else True
            self._execute(
                f"INSERT INTO chat_provider_keys (key_id, athlete_id, provider, api_key_enc, enabled, config_json, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (str(uuid4()), athlete_id, provider, "", enabled_value, raw_json, now, now),
            )

    def save_provider_key(self, athlete_id: str, provider: str, encrypted_key: str, enabled: bool = True, config: dict[str, Any] | None = None) -> None:
        p = self.placeholder
        now = self._now()
        enabled_value = int(enabled) if self.dialect == "firebird" else bool(enabled)
        final_cfg = config
        if final_cfg is None:
            final_cfg = self.get_provider_config(athlete_id, provider)
        raw_json = json.dumps(final_cfg) if final_cfg else None

        cur = self.conn.cursor()
        try:
            cur.execute(f"DELETE FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}", (athlete_id, provider))
            cur.execute(
                f"INSERT INTO chat_provider_keys (key_id, athlete_id, provider, api_key_enc, enabled, config_json, created_at, updated_at) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})",
                (str(uuid4()), athlete_id, provider, encrypted_key, enabled_value, raw_json, now, now),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def list_configured_providers(self, athlete_id: str) -> list[str]:
        p = self.placeholder
        rows = self._all(
            f"SELECT provider, api_key_enc, enabled FROM chat_provider_keys WHERE athlete_id = {p}",
            (athlete_id,),
        )
        result = []
        for row in rows:
            provider = row[0]
            key_enc = row[1]
            enabled = bool(row[2])
            has_key = bool(key_enc and len(str(key_enc).strip()) > 0)
            if (has_key or provider == "ollama") and enabled:
                result.append(provider)
        return result

    def has_provider(self, athlete_id: str, provider: str) -> bool:
        p = self.placeholder
        row = self._one(
            f"SELECT enabled FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}",
            (athlete_id, provider),
        )
        return bool(row and row[0])

    def remove_provider_key(self, athlete_id: str, provider: str) -> None:
        p = self.placeholder
        self._execute(f"DELETE FROM chat_provider_keys WHERE athlete_id = {p} AND provider = {p}", (athlete_id, provider))

    @staticmethod
    def _session(row: tuple) -> ChatSession:
        return ChatSession(*row)

    @staticmethod
    def _message(row: tuple) -> ChatMessage:
        return ChatMessage(*row)



