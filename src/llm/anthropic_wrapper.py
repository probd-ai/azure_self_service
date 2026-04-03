"""
anthropic_wrapper.py — Adapts the Anthropic SDK to BaseLLMClient.

Enable with:  USE_ANTHROPIC=true  in .env

Works with any Claude model that supports tool use:
  claude-3-5-sonnet-20241022, claude-3-opus-20240229, etc.

Key differences from OpenAI that this wrapper handles transparently:
  • System prompt is a separate `system=` param (not in the messages list)
  • Tool schema uses `input_schema` instead of `parameters`
  • stop_reason: "end_turn" | "tool_use"  (vs OpenAI's "stop" | "tool_calls")
  • Tool calls live in `content` blocks, not in a top-level `tool_calls` field
  • Tool results go back as user messages with type "tool_result"
  • Consecutive tool results must be grouped into a single user message

agent.py is completely unaware of all of this — it just calls client.complete()
and reads an AgentResponse, exactly as it does for OpenAI.
"""
import json
from anthropic import Anthropic
from anthropic import RateLimitError as _AntRateLimit
from anthropic import APITimeoutError as _AntTimeout
from anthropic import APIConnectionError as _AntConnError
from anthropic import APIStatusError as _AntStatusError

from src.llm.base import (
    BaseLLMClient, AgentResponse, AgentChoice, AgentMessage, ToolCall, ToolFunction,
    LLMRateLimitError, LLMTimeoutError, LLMConnectionError, LLMStatusError,
)
from src.config.settings import settings


class AnthropicWrapper(BaseLLMClient):
    """
    Adapter that makes the Anthropic Messages API look like BaseLLMClient.

    All OpenAI ↔ Anthropic format conversion happens inside this class.
    Nothing outside this file needs to know Anthropic exists.
    """

    def __init__(self):
        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> AgentResponse:
        # ── 1. Extract system prompt ──────────────────────────────────────────
        # Anthropic takes the system prompt as a separate parameter, not as a
        # message with role="system".
        system_prompt = ""
        non_system = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                non_system.append(m)

        # ── 2. Convert messages and tools to Anthropic format ─────────────────
        anthropic_messages = self._convert_messages(non_system)
        anthropic_tools = self._convert_tools(tools)

        # ── 3. Convert tool_choice ("auto" → {"type": "auto"}) ───────────────
        if isinstance(tool_choice, str):
            anthropic_tool_choice = {"type": tool_choice}   # "auto" or "none"
        else:
            anthropic_tool_choice = tool_choice

        # ── 4. Call the API ───────────────────────────────────────────────────
        try:
            raw = self._client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=anthropic_messages,
                tools=anthropic_tools,
                tool_choice=anthropic_tool_choice,
                temperature=temperature,
            )
        except _AntRateLimit as e:
            raise LLMRateLimitError(str(e)) from e
        except _AntTimeout as e:
            raise LLMTimeoutError(str(e)) from e
        except _AntConnError as e:
            raise LLMConnectionError(str(e)) from e
        except _AntStatusError as e:
            raise LLMStatusError(str(e), e.status_code) from e

        # ── 5. Translate response → AgentResponse ─────────────────────────────
        return self._parse_response(raw)

    # ── Format converters ─────────────────────────────────────────────────────

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert OpenAI-format message list → Anthropic message list.

        OpenAI tool-call assistant turn:
            {"role": "assistant", "content": null,
             "tool_calls": [{"id": "...", "type": "function",
                             "function": {"name": "...", "arguments": "..."}}]}

        Anthropic equivalent:
            {"role": "assistant",
             "content": [{"type": "tool_use", "id": "...",
                           "name": "...", "input": {...}}]}

        OpenAI tool result:
            {"role": "tool", "tool_call_id": "...", "content": "..."}

        Anthropic equivalent (must be a *user* message):
            {"role": "user",
             "content": [{"type": "tool_result",
                           "tool_use_id": "...", "content": "..."}]}

        Multiple consecutive tool results must be grouped into ONE user message.
        """
        result: list[dict] = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m["role"]

            if role == "assistant":
                content_blocks: list[dict] = []
                if m.get("content"):
                    content_blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls", []):
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    })
                result.append({"role": "assistant", "content": content_blocks})

            elif role == "tool":
                # Group all consecutive tool results into one user message
                tool_results: list[dict] = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    t = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": t["tool_call_id"],
                        "content": t["content"],
                    })
                    i += 1
                result.append({"role": "user", "content": tool_results})
                continue  # i already advanced past all tool messages

            else:  # role == "user"
                result.append({"role": "user", "content": m["content"]})

            i += 1

        return result

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """
        Convert OpenAI function-calling tool schema → Anthropic tool schema.

        OpenAI:   {"type": "function", "function": {"name": ..., "description": ...,
                                                     "parameters": {...}}}
        Anthropic: {"name": ..., "description": ..., "input_schema": {...}}
        """
        anthropic_tools: list[dict] = []
        for t in tools:
            fn = t["function"]
            anthropic_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    def _parse_response(self, raw) -> AgentResponse:
        """
        Convert Anthropic response object → AgentResponse.

        Anthropic stop_reason:
          "end_turn"  → finish_reason "stop"     (final answer)
          "tool_use"  → finish_reason "tool_calls" (wants to call a tool)
          "max_tokens"→ finish_reason "stop"      (treat as done)

        Content blocks:
          {"type": "text",     "text": "..."}
          {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
        """
        finish_reason = "tool_calls" if raw.stop_reason == "tool_use" else "stop"

        text_content: str | None = None
        tool_calls: list[ToolCall] = []

        for block in raw.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    function=ToolFunction(
                        name=block.name,
                        arguments=json.dumps(block.input),
                    ),
                ))

        return AgentResponse(choices=[
            AgentChoice(
                finish_reason=finish_reason,
                message=AgentMessage(
                    role="assistant",
                    content=text_content,
                    tool_calls=tool_calls,
                ),
            )
        ])
