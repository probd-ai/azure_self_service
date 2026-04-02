"""
conversation.py — Session and message history management
"""
import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Message:
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list | None = None


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)

    def add(self, role, content, **kwargs):
        self.messages.append(Message(role=role, content=content, **kwargs))

    def to_openai_format(self, max_history: int = 20) -> list[dict]:
        """Convert to OpenAI messages format, keeping last N messages."""
        history = self.messages[-max_history:]
        result = []
        for m in history:
            msg: dict = {"role": m.role, "content": m.content}
            if m.tool_call_id:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            result.append(msg)
        return result


class ConversationManager:
    """In-memory session store. Swap for Redis in production."""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: str | None = None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        session = Session(session_id=session_id or str(uuid.uuid4()))
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str):
        self._sessions.pop(session_id, None)


# Singleton
conversation_manager = ConversationManager()
