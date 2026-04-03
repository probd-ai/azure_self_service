# Integrating a Company's Internal AI Chat Proxy

This guide is written for one specific scenario:

> *Your company has an internal AI chat interface (similar to ChatGPT). It uses Anthropic
> (Claude) models under the hood. You inspected the browser's Network tab, identified the
> API endpoint the frontend hits, and wrote your own Python `requests` script that can call
> it from the command line. You now want to plug that script into this project so the
> Azure Self-Service Agent uses it as its LLM backend.*

**Short answer: yes, it is fully supported.** This is exactly what `src/llm/custom_client.py`
was designed for. This guide walks you through every step.

---

## Table of Contents

1. [How this fits into the project](#1-how-this-fits-into-the-project)
2. [Step 1 — Understand what your proxy returns](#2-step-1--understand-what-your-proxy-returns)
3. [Step 2 — Identify which integration path to use](#3-step-2--identify-which-integration-path-to-use)
4. [Step 3 — Edit custom_client.py](#4-step-3--edit-custom_clientpy)
   - [Path A — Proxy returns OpenAI-format JSON](#path-a--proxy-returns-openai-format-json)
   - [Path B — Proxy returns Anthropic-format JSON](#path-b--proxy-returns-anthropic-format-json)
   - [Path C — Proxy returns a custom/proprietary format](#path-c--proxy-returns-a-customproprietary-format)
   - [Path D — Proxy streams text only (no tool calling)](#path-d--proxy-streams-text-only-no-tool-calling)
5. [Step 4 — Configure .env](#5-step-4--configure-env)
6. [Step 5 — Test the integration](#6-step-5--test-the-integration)
7. [Authentication patterns](#7-authentication-patterns)
8. [Handling streaming responses](#8-handling-streaming-responses)
9. [Tool calling — what it means and what to do if your proxy doesn't support it](#9-tool-calling--what-it-means-and-what-to-do-if-your-proxy-doesnt-support-it)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. How this fits into the project

```
Your existing Python script          This project
─────────────────────────────        ─────────────────────────────────────────
import requests                      src/llm/custom_client.py
                                         └── CustomLLMClient(BaseLLMClient)
resp = requests.post(                          └── complete()
    "https://company-ai.internal/...",                 │
    headers={...},                                     │  your requests code goes here
    json={...}                                         │
)                                                      ▼
                                             returns AgentResponse
                                                       │
                                             agent.py reads it — done
```

You paste your `requests` code into `complete()` inside `CustomLLMClient`. The rest of the
project never changes. The agent calls `client.complete()` the same way regardless of
what is behind it.

---

## 2. Step 1 — Understand what your proxy returns

Before writing any code, you need to know the **response shape** your company's proxy returns.
Open the Network tab in your browser while using the company chat UI, send a message, and
look at the response body of the API call.

### Run this diagnostic on your existing Python script

Add a temporary print to your existing script:

```python
import requests, json

resp = requests.post(
    "https://your-company-ai.internal/api/chat",   # your real endpoint
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={"message": "say hello in 3 words", "model": "claude-3-5-sonnet"},
)

print("Status:", resp.status_code)
print("Headers:", dict(resp.headers))
print(json.dumps(resp.json(), indent=2))
```

Run it and look at the output. Then use the table below to identify which format it is.

### Identifying the response format

**Format 1 — OpenAI-compatible** (the easiest case)

```json
{
  "choices": [
    {
      "finish_reason": "stop",
      "message": {
        "role": "assistant",
        "content": "Hello there friend!"
      }
    }
  ]
}
```

Key tell: top-level `"choices"` array.

---

**Format 2 — Anthropic-native** (common when the proxy forwards Claude responses)

```json
{
  "id": "msg_01...",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "text", "text": "Hello there friend!" }
  ],
  "stop_reason": "end_turn",
  "model": "claude-3-5-sonnet-20241022"
}
```

Key tell: top-level `"content"` array with objects that have a `"type"` field, and `"stop_reason"` instead of `"finish_reason"`.

---

**Format 3 — Custom/proprietary**

```json
{
  "response": "Hello there friend!",
  "status": "complete",
  "session_id": "abc-123"
}
```

Key tell: none of the above — your company defined their own schema.

---

**Format 4 — Streaming text (SSE or chunked)**

The response body is not a single JSON object but a stream of lines like:

```
data: {"delta": {"text": "Hello"}}
data: {"delta": {"text": " there"}}
data: {"delta": {"text": " friend!"}}
data: [DONE]
```

Key tell: `Content-Type: text/event-stream` in response headers, or `Transfer-Encoding: chunked`.

---

## 3. Step 2 — Identify which integration path to use

| What your proxy returns | Path to use | Effort |
|---|---|---|
| OpenAI-format JSON (`"choices"` array) | **Path A** | ~5 min — no parser changes needed |
| Anthropic-format JSON (`"content"` blocks, `"stop_reason"`) | **Path B** | ~15 min — copy the Anthropic parser |
| Custom JSON schema | **Path C** | ~30 min — write a small custom parser |
| Streaming SSE / chunked text only | **Path D** | ~45 min — consume stream + text parsing |

---

## 4. Step 3 — Edit custom_client.py

Open `src/llm/custom_client.py`. The class `CustomLLMClient` is your working area.
Replace the entire class body with the template for your path below.

---

### Path A — Proxy returns OpenAI-format JSON

This is the simplest case. Your proxy already speaks OpenAI's format — you only need to
add your authentication headers. The built-in `_parse_openai_compatible()` parser handles everything.

```python
# src/llm/custom_client.py  ── Path A ──────────────────────────────────────────

import requests
from src.llm.base import BaseLLMClient, AgentResponse
from src.config.settings import settings


class CustomLLMClient(BaseLLMClient):

    def __init__(self):
        self.endpoint = settings.custom_llm_endpoint
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.custom_llm_token}",
            # Add any other headers your company's proxy requires:
            # "X-Company-Client-ID": "azure-self-service",
            # "X-Tenant-ID": "your-tenant-id",
        }
        self.timeout = 120

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "stream": False,
        }
        resp = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_openai_compatible(resp.json())

    # ── inherited from the template — no changes needed ──────────────────────
    # _parse_openai_compatible() is already defined below in the original file
```

---

### Path B — Proxy returns Anthropic-format JSON

Your proxy wraps Claude and forwards the Anthropic response body almost unchanged.
You need to parse the Anthropic content-block format.

```python
# src/llm/custom_client.py  ── Path B ──────────────────────────────────────────

import json
import requests
from src.llm.base import (
    BaseLLMClient, AgentResponse, AgentChoice, AgentMessage,
    ToolCall, ToolFunction,
)
from src.config.settings import settings


class CustomLLMClient(BaseLLMClient):

    def __init__(self):
        self.endpoint = settings.custom_llm_endpoint
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.custom_llm_token}",
        }
        self.timeout = 120

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        # ── Convert messages to whatever format your proxy expects ─────────────
        # If your proxy accepts OpenAI message format → send as-is
        # If it expects Anthropic format → use _to_anthropic_messages() below

        system_prompt = ""
        non_system = []
        for m in messages:
            if m["role"] == "system":
                system_prompt = m["content"]
            else:
                non_system.append(m)

        # Adjust this payload to match what your company proxy expects:
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": self._to_anthropic_messages(non_system),
            "tools": self._to_anthropic_tools(tools),
            "tool_choice": {"type": tool_choice},   # {"type": "auto"}
            "max_tokens": 4096,
            "temperature": temperature,
        }

        resp = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_anthropic_response(resp.json())

    # ── Converters ────────────────────────────────────────────────────────────

    def _to_anthropic_messages(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI message list → Anthropic message list."""
        result = []
        i = 0
        while i < len(messages):
            m = messages[i]
            if m["role"] == "assistant":
                content_blocks = []
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
            elif m["role"] == "tool":
                # Group consecutive tool results into one user message
                tool_results = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    t = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": t["tool_call_id"],
                        "content": t["content"],
                    })
                    i += 1
                result.append({"role": "user", "content": tool_results})
                continue
            else:
                result.append({"role": "user", "content": m["content"]})
            i += 1
        return result

    def _to_anthropic_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI tool schema → Anthropic tool schema."""
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]

    def _parse_anthropic_response(self, data: dict) -> AgentResponse:
        """Parse Anthropic-format response → AgentResponse."""
        finish_reason = "tool_calls" if data.get("stop_reason") == "tool_use" else "stop"
        text_content = None
        tool_calls = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                text_content = block["text"]
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block["id"],
                    function=ToolFunction(
                        name=block["name"],
                        arguments=json.dumps(block["input"]),
                    ),
                ))

        return AgentResponse(choices=[AgentChoice(
            finish_reason=finish_reason,
            message=AgentMessage(
                role="assistant",
                content=text_content,
                tool_calls=tool_calls,
            ),
        )])
```

---

### Path C — Proxy returns a custom/proprietary format

Your company's API team designed their own schema. Map their fields to `AgentResponse`.

```python
# src/llm/custom_client.py  ── Path C ──────────────────────────────────────────
# Example: company proxy returns {"response": "...", "status": "complete", "actions": [...]}

import json, uuid
import requests
from src.llm.base import (
    BaseLLMClient, AgentResponse, AgentChoice, AgentMessage,
    ToolCall, ToolFunction,
)
from src.config.settings import settings


class CustomLLMClient(BaseLLMClient):

    def __init__(self):
        self.endpoint = settings.custom_llm_endpoint
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.custom_llm_token}",
        }
        self.timeout = 120

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        # Build the payload in whatever format YOUR proxy expects.
        # Look at your existing Python script — copy that payload here.
        payload = {
            "prompt": messages[-1]["content"],      # example: only sends the latest message
            "history": messages[:-1],               # example: sends history separately
            "model": model,
        }

        resp = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_custom_response(resp.json())

    def _parse_custom_response(self, data: dict) -> AgentResponse:
        # Map YOUR proxy's response fields to AgentResponse.
        # Adjust field names to match what your proxy actually returns.

        reply_text = data.get("response") or data.get("text") or data.get("message") or ""
        is_done = data.get("status") == "complete"

        # If your proxy never returns tool calls → always return "stop"
        return AgentResponse(choices=[AgentChoice(
            finish_reason="stop",
            message=AgentMessage(
                role="assistant",
                content=reply_text,
                tool_calls=[],
            ),
        )])

        # If your proxy CAN return structured actions/tool calls, map them here:
        # tool_calls = []
        # for action in data.get("actions", []):
        #     tool_calls.append(ToolCall(
        #         id=action.get("id", str(uuid.uuid4())),
        #         function=ToolFunction(
        #             name=action["tool"],
        #             arguments=json.dumps(action["parameters"]),
        #         ),
        #     ))
        # finish_reason = "tool_calls" if tool_calls else "stop"
        # return AgentResponse(choices=[AgentChoice(
        #     finish_reason=finish_reason,
        #     message=AgentMessage(role="assistant", content=reply_text or None, tool_calls=tool_calls),
        # )])
```

---

### Path D — Proxy streams text only (no tool calling)

Your proxy only returns a plain text stream — no structured tool calling. This is the
most limited case. The agent still works, but it uses a text parsing fallback instead of
native tool calling. The model must be smart enough to output JSON tool-call blocks in
its text when it wants to use a tool.

```python
# src/llm/custom_client.py  ── Path D ──────────────────────────────────────────

import json, uuid
import requests
from src.llm.base import BaseLLMClient, AgentResponse
from src.config.settings import settings


class CustomLLMClient(BaseLLMClient):

    def __init__(self):
        self.endpoint = settings.custom_llm_endpoint
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.custom_llm_token}",
        }
        self.timeout = 120

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        # Send only the messages — no tools in payload (your proxy doesn't support them)
        # Include tool definitions in the system message text instead
        tool_instructions = self._tools_as_text(tools)
        augmented_messages = []
        for m in messages:
            if m["role"] == "system":
                augmented_messages.append({
                    "role": "system",
                    "content": m["content"] + "\n\n" + tool_instructions,
                })
            else:
                augmented_messages.append(m)

        payload = {
            "model": model,
            "messages": augmented_messages,
            "temperature": temperature,
            "stream": False,
        }

        resp = requests.post(self.endpoint, json=payload, headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()

        # Extract the text reply — adjust the field path to match your proxy
        data = resp.json()
        reply_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content")  # OpenAI-style
            or data.get("response")                                           # custom style
            or data.get("content", [{}])[0].get("text", "")                  # Anthropic-style
        )

        # Parse any tool-call intent from the text
        return self._parse_text_for_tool_calls(reply_text)

    def _tools_as_text(self, tools: list[dict]) -> str:
        """Describe available tools in plain text so the model knows what it can call."""
        lines = [
            "You have access to the following tools. When you want to call one, output "
            "ONLY a JSON block in this exact format and nothing else:\n"
            '{"tool": "<tool_name>", "args": {<arguments>}}\n\n'
            "Available tools:"
        ]
        for t in tools:
            fn = t["function"]
            params = ", ".join(fn.get("parameters", {}).get("properties", {}).keys())
            lines.append(f'  - {fn["name"]}({params}): {fn.get("description", "")}')
        return "\n".join(lines)

    # _parse_text_for_tool_calls() is inherited from the base template
```

> ⚠️ **Path D limitation:** Because the proxy doesn't natively support tool calling, the
> agent relies on the model to output a specific JSON format in plain text. This is less
> reliable than native tool calling. Weaker models may not follow the format consistently.
> If you can switch to a path that has native tool support, do so.

---

## 5. Step 4 — Configure .env

```env
# ── Disable all other providers ───────────────────────────────────────────────
USE_COXY=false
USE_AZURE_OPENAI=false
USE_ANTHROPIC=false

# ── Enable your company proxy ─────────────────────────────────────────────────
USE_CUSTOM_LLM=true

# The endpoint your company chat UI calls (from the Network tab)
CUSTOM_LLM_ENDPOINT=https://company-ai.internal/api/v1/chat/completions

# Your auth token / session token (see Section 7 for different auth types)
CUSTOM_LLM_TOKEN=eyJhbGciOiJSUzI1NiJ9...your-jwt-or-bearer-token...

# The model name your proxy expects (check the Network tab request payload)
CUSTOM_LLM_MODEL=claude-3-5-sonnet-20241022
```

---

## 6. Step 5 — Test the integration

### 6.1 Unit test your custom_client.py in isolation

Run this before starting the full agent:

```bash
cd /path/to/Azure_self_service
source .venv/bin/activate

python - <<'EOF'
import sys
sys.path.insert(0, ".")

from src.llm.custom_client import CustomLLMClient

client = CustomLLMClient()

# Minimal test — single message, no tools
response = client.complete(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Reply with exactly: PROXY_WORKS"}
    ],
    tools=[],
    tool_choice="auto",
    temperature=0.0,
)

print("finish_reason:", response.choices[0].finish_reason)
print("content:", response.choices[0].message.content)
EOF
```

Expected output:
```
finish_reason: stop
content: PROXY_WORKS
```

### 6.2 Test tool calling

```bash
python - <<'EOF'
import sys, json
sys.path.insert(0, ".")

from src.llm.custom_client import CustomLLMClient

client = CustomLLMClient()

TOOLS = [{
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "List contents of a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"}
            },
            "required": ["path"]
        }
    }
}]

response = client.complete(
    model="claude-3-5-sonnet-20241022",
    messages=[
        {"role": "system", "content": "Use list_directory when asked to list files."},
        {"role": "user",   "content": "List the terraform/ directory."}
    ],
    tools=TOOLS,
    tool_choice="auto",
    temperature=0.0,
)

choice = response.choices[0]
print("finish_reason:", choice.finish_reason)
if choice.finish_reason == "tool_calls":
    tc = choice.message.tool_calls[0]
    print("tool name:", tc.function.name)
    print("tool args:", tc.function.arguments)
else:
    print("content:", choice.message.content)
EOF
```

Expected output (if tool calling works):
```
finish_reason: tool_calls
tool name: list_directory
tool args: {"path": "terraform/"}
```

### 6.3 Start the full agent and test end-to-end

```bash
python main.py
```

Then in another terminal:

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what azure services can I deploy?"}' | python3 -m json.tool
```

---

## 7. Authentication patterns

### Bearer token (JWT)

Most company SSO systems issue JWTs. Copy the token from the `Authorization` header in the Network tab.

```python
self.headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {settings.custom_llm_token}",
}
```

```env
CUSTOM_LLM_TOKEN=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

> ⚠️ JWTs expire. If requests start returning 401, you need a fresh token.
> See Section 10 for how to handle token refresh automatically.

---

### Session cookie

Some internal tools authenticate via browser cookies rather than `Authorization` headers.

```python
# In your existing Python script you may have found something like:
# Cookie: session=abc123; __cf_bm=xyz
self.headers = {
    "Content-Type": "application/json",
    "Cookie": f"session={settings.custom_llm_token}",
}
```

Or use `requests.Session` with a cookie jar:

```python
import requests

class CustomLLMClient(BaseLLMClient):
    def __init__(self):
        self.session = requests.Session()
        self.session.cookies.set("session", settings.custom_llm_token)
        self.session.headers.update({"Content-Type": "application/json"})
        self.endpoint = settings.custom_llm_endpoint
        self.timeout = 120

    def complete(self, ...):
        resp = self.session.post(self.endpoint, json=payload, timeout=self.timeout)
        ...
```

---

### API key in custom header

Some internal proxies use a custom header instead of `Authorization`:

```python
self.headers = {
    "Content-Type": "application/json",
    "X-API-Key": settings.custom_llm_token,
    # or: "X-Internal-Token": settings.custom_llm_token,
    # or: "X-Company-Auth": settings.custom_llm_token,
}
```

---

### Multiple headers (common in enterprise proxies)

Enterprise proxies often require several headers. Copy the exact headers from your Network tab.

```python
self.headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {settings.custom_llm_token}",
    "X-Tenant-ID":   "your-company-tenant-id",
    "X-Client-Name": "azure-self-service-agent",
    "X-Environment": "production",
}
```

---

## 8. Handling streaming responses

Many company chat UIs use streaming (SSE) to show text as it's generated. The
`stream: False` payload flag tells most proxies to return everything in one response.

If your proxy **ignores** `stream: False` and always streams, consume the stream manually:

```python
def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "temperature": temperature,
        "stream": True,     # proxy forces streaming
    }

    full_text = ""
    with requests.post(
        self.endpoint,
        json=payload,
        headers=self.headers,
        timeout=self.timeout,
        stream=True,           # consume incrementally
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
            if line in ("[DONE]", ""):
                continue
            try:
                chunk = json.loads(line)
                # OpenAI streaming format:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                full_text += delta.get("content", "")
                # Anthropic streaming format:
                # full_text += chunk.get("delta", {}).get("text", "")
            except json.JSONDecodeError:
                pass

    # Streaming proxies rarely support tool calling — use text parser
    return self._parse_text_for_tool_calls(full_text)
```

---

## 9. Tool calling — what it means and what to do if your proxy doesn't support it

### What tool calling is

When the agent asks "what can I deploy?", it doesn't know the answer from memory.
Instead it calls tools:

```
Agent → LLM: "user wants to know available services. Tools: list_directory, read_file"
LLM → Agent: "call list_directory with path='terraform/'"
Agent: runs list_directory("terraform/") → ["aks/", "vnet/", ...]
Agent → LLM: "here is what list_directory returned: [aks/, vnet/, ...]"
LLM → Agent: "I now have enough info. Final answer: you can deploy AKS, VNet, ..."
```

The LLM must signal "I want to call a tool" in a structured way the agent can read.
This is called **native tool calling** and is built into modern APIs.

### If your proxy SUPPORTS tool calling (same API as Anthropic or OpenAI)

Use Path A or Path B above. The proxy accepts a `tools` array in the request and returns
tool-call blocks in the response. This is the best case.

**How to confirm:** Send a test request with a `tools` array and a message that should
trigger a tool. If the response contains `"tool_use"` blocks (Anthropic) or
`"tool_calls"` (OpenAI), tool calling is supported.

### If your proxy DOES NOT support tool calling

Use Path D. The agent sends tool descriptions as plain text in the system prompt and
asks the model to output a specific JSON format when it wants to call a tool:

```
{"tool": "list_directory", "args": {"path": "terraform/"}}
```

The agent's `_parse_text_for_tool_calls()` method detects this pattern and extracts it.

**Limitation:** This is less reliable. The model must follow the format exactly every time.
With Claude behind the proxy, this usually works well. With weaker models it may break.

### If tool calling is partially working

If the agent loops forever calling the same tool, or never produces a final answer, the
most common cause is the proxy silently stripping the `tools` field from your request.
Add a debug print:

```python
def complete(self, ...):
    print("[DEBUG] payload tools:", json.dumps(tools[:1], indent=2))  # print first tool
    resp = requests.post(...)
    print("[DEBUG] response:", json.dumps(resp.json(), indent=2)[:500])
    ...
```

Check whether the response body contains any tool-call related fields.

---

## 10. Troubleshooting

### `401 Unauthorized`

Your token is wrong or expired.

- Copy a fresh token from the Network tab (filter by your API endpoint, click the request,
  look at the `Authorization` request header)
- Paste it into `CUSTOM_LLM_TOKEN` in `.env`
- JWTs typically expire in 1–24 hours depending on your company's policy

---

### `403 Forbidden`

Your token is valid but the proxy is blocking the request for another reason:

- Wrong tenant / wrong scopes on the JWT
- A required header is missing (check all request headers in the Network tab)
- Your IP or environment is not whitelisted (the proxy may only allow corporate VPN)

---

### `422 Unprocessable Entity`

The payload shape is wrong — the proxy rejected the JSON body.

- Print the full request payload and compare it to what the browser sends in the Network tab
- The proxy may expect fields named differently (e.g. `"prompt"` instead of `"messages"`)
- The proxy may require extra fields (`"session_id"`, `"user_id"`, etc.)

---

### Response parses to `finish_reason: stop` but content is `None` or empty

Your parser is reading the wrong field. Print `resp.json()` and trace which key holds the text:

```python
data = resp.json()
print(json.dumps(data, indent=2))  # find the text field
```

Then update `_parse_custom_response()` to read the correct key.

---

### Agent loops forever without giving a final answer

Tool calling is not working. The model calls the same tool repeatedly or never stops.

1. Confirm `finish_reason` is being returned correctly (should be `"stop"` when done)
2. Confirm tool results are being sent back to the proxy in the correct format
3. Add `print("[DEBUG]", response.choices[0].finish_reason)` at the top of the agent loop
4. Switch to Path D (text parsing) if the proxy doesn't support native tool calling

---

### `SSLError` or certificate error

The company proxy uses a self-signed or internal CA certificate.

```python
resp = requests.post(
    self.endpoint,
    json=payload,
    headers=self.headers,
    timeout=self.timeout,
    verify="/path/to/company-ca-bundle.crt",   # your company's CA cert
    # OR for testing only (NOT production):
    # verify=False,
)
```

---

### Token refresh — keeping the session alive automatically

If your token expires frequently, add auto-refresh logic:

```python
import time

class CustomLLMClient(BaseLLMClient):

    def __init__(self):
        self.endpoint = settings.custom_llm_endpoint
        self.timeout = 120
        self._token = settings.custom_llm_token
        self._token_expiry = float("inf")   # set from JWT exp claim if known

    def _get_headers(self) -> dict:
        if time.time() > self._token_expiry - 60:
            self._token = self._refresh_token()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    def _refresh_token(self) -> str:
        # Call your company's token refresh endpoint here
        resp = requests.post(
            "https://company-auth.internal/oauth/token",
            json={"grant_type": "refresh_token", "refresh_token": "YOUR_REFRESH_TOKEN"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token_expiry = time.time() + data["expires_in"]
        return data["access_token"]

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        resp = requests.post(
            self.endpoint,
            json={...},
            headers=self._get_headers(),   # ← uses fresh token automatically
            timeout=self.timeout,
        )
        ...
```
