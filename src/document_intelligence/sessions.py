import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChatSession:
    id: str
    document_ids: list[str]
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    busy: bool = False
    last_used: float = field(default_factory=time.monotonic, repr=False)

    def public(self) -> dict:
        return {
            "id": self.id,
            "document_ids": self.document_ids,
            "history": self.history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "busy": self.busy,
        }


class SessionManager:
    def __init__(self, max_history_messages: int = 20, ttl_seconds: int = 0):
        self.max_history_messages = max_history_messages
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.RLock()

    def _purge_expired(self) -> None:
        if self.ttl_seconds <= 0:
            return
        cutoff = time.monotonic() - self.ttl_seconds
        for key in [
            key
            for key, item in self._sessions.items()
            if not item.busy and item.last_used < cutoff
        ]:
            del self._sessions[key]

    def create(self, document_ids: list[str]) -> ChatSession:
        if not document_ids:
            raise ValueError("Select at least one document.")
        session = ChatSession(
            id=str(uuid.uuid4()), document_ids=list(dict.fromkeys(document_ids))
        )
        with self._lock:
            self._purge_expired()
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> ChatSession:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            session.last_used = time.monotonic()
            return session

    def update_documents(self, session_id: str, document_ids: list[str]) -> ChatSession:
        if not document_ids:
            raise ValueError("Select at least one document.")
        with self._lock:
            session = self.get(session_id)
            if session.busy:
                raise RuntimeError("The session is processing another message.")
            session.document_ids = list(dict.fromkeys(document_ids))
            session.history.clear()
            session.updated_at = utc_now()
            return session

    def begin_message(self, session_id: str) -> tuple[list[str], list[dict[str, str]]]:
        with self._lock:
            session = self.get(session_id)
            if session.busy:
                raise RuntimeError("The session is processing another message.")
            session.busy = True
            return list(session.document_ids), list(session.history)

    def complete_message(self, session_id: str, question: str, answer: str) -> None:
        with self._lock:
            session = self.get(session_id)
            session.history.extend(
                [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ]
            )
            session.history = session.history[-self.max_history_messages :]
            session.updated_at = utc_now()
            session.busy = False

    def fail_message(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.busy = False
                session.updated_at = utc_now()

    def delete(self, session_id: str) -> None:
        with self._lock:
            if self._sessions.pop(session_id, None) is None:
                raise KeyError(session_id)
