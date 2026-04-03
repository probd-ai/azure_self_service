"""
custom_client.py — Plug in YOUR OWN LLM backend here.

Enable with:  USE_CUSTOM_LLM=true  in .env

How to use
----------
1. Set USE_CUSTOM_LLM=true in .env  (all other USE_* must be false)
2. Edit the CustomLLMClient class below to call your endpoint
3. The agent automatically picks this up — no other file needs changing

What you must do
----------------
• Implement complete() — call your endpoint, parse the response,
  return an AgentResponse.

• Your endpoint must support tool/function calling in SOME form.
  See the two examples below:
    A) OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, ChatGPT web via reverse proxy)
    B) Non-compatible endpoint (custom model, proprietary API)
       → you parse the text output yourself and construct tool calls

The agent only ever calls client.complete() and reads AgentResponse.
It does not care what lives inside this file.
"""
import json
import uuid
import requests

from src.llm.base import BaseLLMClient, AgentResponse, AgentChoice, AgentMessage, ToolCall, ToolFunction


class CustomLLMClient(BaseLLMClient):
    """
    Template for a custom LLM backend.

    Edit __init__ to configure your endpoint/credentials.
    Edit complete() to call your endpoint and return AgentResponse.
    """

    def __init__(self):
        # ── Configure your endpoint here ──────────────────────────────────────
        # Option A: OpenAI-compatible local model (Ollama, vLLM, LM Studio)
        self.endpoint = "http://localhost:11434/v1/chat/completions"

        # Option B: ChatGPT web via session token (unofficial)
        # self.endpoint = "https://chatgpt.com/backend-api/conversation"

        # Option C: Any other HTTP API
        # self.endpoint = "https://your-api.example.com/v1/chat"

        self.headers = {
            "Content-Type": "application/json",
            # Add auth here:
            # "Authorization": "Bearer YOUR_TOKEN",
            # "Cookie": "__Secure-next-auth.session-token=YOUR_SESSION_TOKEN",
        }
        self.timeout = 120  # seconds

    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> AgentResponse:
        """
        Call your custom LLM and return AgentResponse.

        Two paths:
          A) Endpoint supports OpenAI tool-calling → use _parse_openai_compatible()
          B) Endpoint returns plain text → use _parse_text_for_tool_calls()
        """
        # ── PATH A: OpenAI-compatible endpoint ────────────────────────────────
        # Works with: Ollama (llama3, mistral, etc.), vLLM, LM Studio, any
        # endpoint that accepts the OpenAI /v1/chat/completions payload.

        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "stream": False,
        }

        resp = requests.post(
            self.endpoint,
            json=payload,
            headers=self.headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        return self._parse_openai_compatible(data)

        # ── PATH B: Non-compatible endpoint ───────────────────────────────────
        # If your endpoint doesn't support tool_calling, comment out PATH A above
        # and uncomment PATH B. You send plain messages, get plain text back,
        # and parse the text yourself to detect tool call intent.

        # payload = {
        #     "model": model,
        #     "messages": messages,   # no tools/tool_choice in payload
        #     "temperature": temperature,
        # }
        # resp = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
        # resp.raise_for_status()
        # reply_text = resp.json()["choices"][0]["message"]["content"]
        # return self._parse_text_for_tool_calls(reply_text)

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _parse_openai_compatible(self, data: dict) -> AgentResponse:
        """Parse a standard OpenAI-shaped response dict."""
        choices = []
        for raw_choice in data.get("choices", []):
            raw_msg = raw_choice.get("message", {})
            tool_calls: list[ToolCall] = []
            for tc in raw_msg.get("tool_calls") or []:
                tool_calls.append(ToolCall(
                    id=tc.get("id", str(uuid.uuid4())),
                    function=ToolFunction(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                ))
            choices.append(AgentChoice(
                finish_reason=raw_choice.get("finish_reason", "stop"),
                message=AgentMessage(
                    role=raw_msg.get("role", "assistant"),
                    content=raw_msg.get("content"),
                    tool_calls=tool_calls,
                ),
            ))
        return AgentResponse(choices=choices)

    def _parse_text_for_tool_calls(self, reply_text: str) -> AgentResponse:
        """
        Fallback parser for models that don't support native tool calling.

        Looks for JSON blocks in the model's text output that match the pattern:
            {"tool": "list_directory", "args": {"path": "terraform/"}}

        If found → returns finish_reason="tool_calls"
        If not   → returns finish_reason="stop" with the plain text reply
        """
        try:
            # Look for a JSON block starting with {"tool":
            start = reply_text.index('{"tool"')
            end = reply_text.rindex("}") + 1
            tool_json = json.loads(reply_text[start:end])
            tool_name = tool_json["tool"]
            tool_args = tool_json.get("args", {})

            return AgentResponse(choices=[AgentChoice(
                finish_reason="tool_calls",
                message=AgentMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[ToolCall(
                        id=str(uuid.uuid4()),
                        function=ToolFunction(
                            name=tool_name,
                            arguments=json.dumps(tool_args),
                        ),
                    )],
                ),
            )])
        except (ValueError, KeyError):
            # No tool call found — treat as a plain final answer
            return AgentResponse(choices=[AgentChoice(
                finish_reason="stop",
                message=AgentMessage(
                    role="assistant",
                    content=reply_text,
                    tool_calls=[],
                ),
            )])
