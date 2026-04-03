"""
base.py — Standard LLM interface used by agent.py

Every LLM client (OpenAI, Azure, Coxy, custom requests-based) must:
  1. Subclass BaseLLMClient
  2. Implement complete() returning AgentResponse

agent.py never imports openai or requests directly —
it only ever calls client.complete() and reads AgentResponse.
This means you can swap the entire LLM backend by changing one env var.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Response shape ────────────────────────────────────────────────────────────
# These dataclasses mirror the OpenAI SDK response structure but are
# completely independent of it — no openai import required.

@dataclass
class ToolFunction:
    """The name + serialised JSON arguments of one tool call."""
    name: str
    arguments: str          # raw JSON string, e.g. '{"path": "terraform/"}'


@dataclass
class ToolCall:
    """One tool-call request from the LLM."""
    id: str                 # unique call ID (must be echoed back in the tool result)
    function: ToolFunction
    type: str = "function"


@dataclass
class AgentMessage:
    """The message object inside one choice."""
    role: str               # "assistant"
    content: str | None     # text reply, or None when tool_calls is set
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AgentChoice:
    """One candidate completion."""
    finish_reason: str      # "stop" → final answer | "tool_calls" → LLM wants a tool
    message: AgentMessage


@dataclass
class AgentResponse:
    """Top-level response from any LLM client."""
    choices: list[AgentChoice]


# ── Abstract client ───────────────────────────────────────────────────────────

class BaseLLMClient(ABC):
    """
    Every LLM backend must implement this single method.

    Parameters
    ----------
    model        : model identifier (name, deployment name, etc.)
    messages     : full conversation so far in OpenAI message format
    tools        : tool definitions in OpenAI function-calling format
    tool_choice  : "auto" | "none" | {"type":"function","function":{"name":"..."}}
    temperature  : 0.0–2.0

    Returns
    -------
    AgentResponse — agent.py reads choices[0] to decide next action
    """

    @abstractmethod
    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> AgentResponse:
        ...


# ── Unified LLM error classes ─────────────────────────────────────────────────
# Both OpenAI and Anthropic wrappers catch their SDK-specific errors and
# re-raise these, so agent.py only ever handles one consistent set.

class LLMRateLimitError(Exception):
    """API rate limit hit — ask the user to wait and retry."""


class LLMTimeoutError(Exception):
    """Request timed out."""


class LLMConnectionError(Exception):
    """Cannot reach the LLM backend (wrong URL, service down, etc.)."""


class LLMStatusError(Exception):
    """The LLM API returned an HTTP error status."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
