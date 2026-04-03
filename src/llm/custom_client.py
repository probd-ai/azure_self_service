"""
custom_client.py — Bridges the company's internal LLM client into this project.

Setup
─────
Place the company's Python files directly into src/llm/:

    src/llm/client.py      ← must contain get_llm_client()
    src/llm/config.py      ← must contain LLMConfig
    src/llm/models.py      ← contains LLMResponse, etc.
    src/llm/exceptions.py  ← contains InvalidResponseError, etc.

⚠️  The company also ships a base.py — rename it to company_base.py before
    placing it here, because this project already has src/llm/base.py.

How the company client works
─────────────────────────────
    from src.llm.client import get_llm_client
    from src.llm.config import LLMConfig

    config = LLMConfig(...)
    client = get_llm_client(config)

    response = client.query("say hello")          # → LLMResponse
    print(response.content)                       # → str  (the reply text)

    # or for JSON responses:
    data = client.query_json("return JSON ...")   # → dict

Under the hood (from LLMManager.query):
    POST {base_url}/api/chat/agent?conversation_id=<id>&model=<model>
    Body: {"prompt": "<text>"}                    ← plain string, NOT messages array
    Reply is NOT in the POST body — fetched via _get_messages(conversation_id)

The company client has NO native tool calling. This adapter injects tool
definitions as plain-text instructions and parses JSON blocks from the reply.

Enable with:  USE_CUSTOM_LLM=true  in .env
"""
import json
import uuid

# ── Company client imports ─────────────────────────────────────────────────────
# The company's files are placed directly in src/llm/ — import them here.
from src.llm.client import get_llm_client          # company's factory function
from src.llm.config import LLMConfig               # company's config dataclass

# ── This project's base classes (do NOT confuse with company's base.py) ────────
from src.llm.base import (
    BaseLLMClient,
    AgentResponse, AgentChoice, AgentMessage, ToolCall, ToolFunction,
)
from src.config.settings import settings


class CustomLLMClient(BaseLLMClient):
    """
    Adapts the company's get_llm_client() into BaseLLMClient so agent.py
    can use it without any changes.

    What this adapter does:
      1. Builds a LLMConfig from .env settings and calls get_llm_client(config)
      2. Creates one conversation_id per agent run, reused across all tool-call
         iterations so the proxy keeps server-side history in sync
      3. Flattens the OpenAI messages list + tool definitions → single prompt string
      4. Calls client.query(prompt, conversation_id) → LLMResponse
      5. Reads LLMResponse.content (plain text string)
      6. Parses {"tool": "...", "args": {...}} JSON blocks from the text
    """

    def __init__(self):
        # Build config — adjust field names to match the actual LLMConfig dataclass.
        # Open src/llm/config.py to see the exact field names, then update below.
        config = LLMConfig(
            api_key  = settings.custom_llm_token,       # or: token=, key=, auth=
            base_url = settings.custom_llm_endpoint,    # or: url=, endpoint=, host=
            model_id = settings.custom_llm_model,       # or: model=, model_name=
            timeout  = 120,                             # or omit if not a LLMConfig field
        )
        # Initialise client — same as: client = get_llm_client(config)
        self._client = get_llm_client(config)

        # One conversation_id per agent run; created on the first complete() call
        self._conversation_id: str | None = None

    # ── complete() — called by agent.py on every LLM iteration ───────────────

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> AgentResponse:
        # Start a conversation once, reuse the ID on all subsequent iterations
        # so the proxy's server-side history stays consistent.
        if self._conversation_id is None:
            self._conversation_id = self._client.create_conversation()

        # Flatten messages + tool definitions into one prompt string.
        prompt = self._build_prompt(messages, tools)

        # Call the company client — same pattern as existing scripts:
        #   response = client.query("say hello")
        #   print(response.content)
        llm_response = self._client.query(
            prompt,
            conversation_id=self._conversation_id,
        )

        # llm_response.content is a plain text string.
        # Parse it for a JSON tool-call block, or treat as the final answer.
        return self._parse_text_for_tool_calls(llm_response.content)

    # ── Prompt builder ────────────────────────────────────────────────────────

    def _build_prompt(self, messages: list[dict], tools: list[dict]) -> str:
        """
        Converts the OpenAI-format messages list + tool definitions into a
        single prompt string for client.query().

        Layout:
          [system prompt]
          [tool instructions — only when tools are present]
          [conversation history — User/Assistant/Tool result turns]
          User: <latest user message>
        """
        parts: list[str] = []

        system_text = ""
        non_system: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            else:
                non_system.append(m)

        if system_text:
            parts.append(system_text)

        if tools:
            parts.append(self._tools_as_instructions(tools))

        # History — all turns except the last user message
        for m in non_system[:-1]:
            role = m["role"]
            if role == "user":
                parts.append(f"User: {m['content']}")
            elif role == "assistant":
                content = m.get("content") or ""
                tool_calls = m.get("tool_calls", [])
                if tool_calls and not content:
                    names = ", ".join(tc["function"]["name"] for tc in tool_calls)
                    content = f"[called tools: {names}]"
                parts.append(f"Assistant: {content}")
            elif role == "tool":
                parts.append(f"Tool result: {m['content']}")

        # Latest user message
        if non_system and non_system[-1]["role"] == "user":
            parts.append(f"User: {non_system[-1]['content']}")

        return "\n\n".join(parts)

    def _tools_as_instructions(self, tools: list[dict]) -> str:
        """
        Converts OpenAI tool definitions into plain-text instructions so the
        model knows what tools exist and how to signal it wants to call one.

        The model must output exactly this JSON (and nothing else) on that turn:
            {"tool": "<name>", "args": {<key>: <value>}}

        _parse_text_for_tool_calls() detects and extracts that block.
        """
        lines = [
            "=== AVAILABLE TOOLS ===",
            "To call a tool, output ONLY this JSON on its own line — no other text:\n"
            '{"tool": "<tool_name>", "args": {<key>: <value>}}\n',
            "Wait for the tool result before writing your final answer.\n",
            "Tools:",
        ]
        for t in tools:
            fn = t["function"]
            props = fn.get("parameters", {}).get("properties", {})
            required = fn.get("parameters", {}).get("required", [])
            param_parts = [
                f"{k}({'required' if k in required else 'optional'}): "
                f"{v.get('description', v.get('type', ''))}"
                for k, v in props.items()
            ]
            lines.append(f"  • {fn['name']}({', '.join(param_parts)})")
            lines.append(f"    {fn.get('description', '')}")
        lines.append("=== END TOOLS ===")
        return "\n".join(lines)

    # ── Response parser ───────────────────────────────────────────────────────

    def _parse_text_for_tool_calls(self, reply_text: str) -> AgentResponse:
        """
        Scans the model's text reply for a JSON tool-call block:
            {"tool": "list_directory", "args": {"path": "terraform/"}}

        Found     → finish_reason="tool_calls"  agent.py runs the tool and loops
        Not found → finish_reason="stop"        agent.py returns the text to the user
        """
        try:
            start = reply_text.index('{"tool"')
            end   = reply_text.rindex("}") + 1
            tool_json = json.loads(reply_text[start:end])
            return AgentResponse(choices=[AgentChoice(
                finish_reason="tool_calls",
                message=AgentMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCall(
                        id=str(uuid.uuid4()),
                        function=ToolFunction(
                            name=tool_json["tool"],
                            arguments=json.dumps(tool_json.get("args", {})),
                        ),
                    )],
                ),
            )])
        except (ValueError, KeyError):
            # No tool-call block found — this is the final answer
            return AgentResponse(choices=[AgentChoice(
                finish_reason="stop",
                message=AgentMessage(
                    role="assistant",
                    content=reply_text,
                    tool_calls=[],
                ),
            )])
