# LLM Setup & User Guide

Complete reference for every LLM backend supported by the Azure Self-Service Agent.
Switch providers any time — no code changes, just edit `.env` and restart.

---

## Table of Contents

1. [How the LLM layer works](#1-how-the-llm-layer-works)
2. [Ground rule — only ONE provider at a time](#2-ground-rule--only-one-provider-at-a-time)
3. [Option 1 — Coxy / GitHub Copilot (free)](#3-option-1--coxy--github-copilot-free)
4. [Option 2 — Azure OpenAI (production)](#4-option-2--azure-openai-production)
5. [Option 3 — Standard OpenAI (ChatGPT)](#5-option-3--standard-openai-chatgpt)
6. [Option 4 — Anthropic / Claude](#6-option-4--anthropic--claude)
7. [Option 5 — Custom LLM (Ollama, vLLM, LM Studio, any HTTP API)](#7-option-5--custom-llm-ollama-vllm-lm-studio-any-http-api)
8. [Model recommendations by use case](#8-model-recommendations-by-use-case)
9. [Developer guide — adding a new LLM backend](#9-developer-guide--adding-a-new-llm-backend)
10. [Troubleshooting by provider](#10-troubleshooting-by-provider)

---

## 1. How the LLM layer works

```
.env (USE_ANTHROPIC=true, etc.)
        │
        ▼
agent.py → _get_client()          ← factory: picks the right backend
        │
        ▼
BaseLLMClient.complete()          ← every backend implements this one method
        │
        ├── OpenAIWrapper          (Coxy, Azure OpenAI, standard OpenAI)
        ├── AnthropicWrapper       (Claude models)
        └── CustomLLMClient        (Ollama, vLLM, LM Studio, any HTTP API)
        │
        ▼
AgentResponse                     ← unified response — agent.py never touches SDK objects
```

**Key design:** `agent.py` is 100% SDK-agnostic. It calls `client.complete()` and reads
`AgentResponse` dataclasses — the same object shape regardless of which LLM is behind it.
All format conversion (Anthropic tool schemas, Azure endpoints, etc.) happens inside each
wrapper, invisible to the rest of the app.

---

## 2. Ground rule — only ONE provider at a time

All `USE_*` flags default to `false`. Set **exactly one** to `true`.

| Flag | Default |
|---|---|
| `USE_COXY` | false |
| `USE_AZURE_OPENAI` | false |
| `USE_ANTHROPIC` | false |
| `USE_CUSTOM_LLM` | false |
| *(none of the above)* | → standard OpenAI is used |

If two flags are accidentally set to `true`, this is the priority order the factory follows:

```
USE_CUSTOM_LLM  >  USE_ANTHROPIC  >  USE_COXY  >  USE_AZURE_OPENAI  >  OpenAI (default)
```

---

## 3. Option 1 — Coxy / GitHub Copilot *(free)*

**Best for:** Local development, POC, anyone with a GitHub Copilot subscription.
**Cost:** Free (uses your existing Copilot quota).
**Requires:** Docker, active GitHub Copilot Individual/Business/Enterprise subscription.

### 3.1 What is Coxy?

Coxy is a tiny Docker container that exposes your GitHub Copilot subscription as a local
OpenAI-compatible API at `http://localhost:3000`. The agent talks to it exactly like it
would talk to OpenAI — Coxy translates everything behind the scenes.

### 3.2 First-time setup (do this once)

#### Step 1 — Create a persistent token database

```bash
mkdir -p .coxy && touch .coxy/coxy.db
```

#### Step 2 — Initialise the DB schema

```bash
docker run --rm \
  -e DATABASE_URL="file:/app/coxy.db" \
  -v $(pwd)/.coxy/coxy.db:/app/coxy.db \
  ghcr.io/coxy-proxy/coxy:latest --provision
```

Expected output: `The database is already in sync with the Prisma schema.`

#### Step 3 — Start Coxy

```bash
docker run -d \
  --name coxy \
  -p 3000:3000 \
  -e DATABASE_URL="file:/app/coxy.db" \
  -v $(pwd)/.coxy/coxy.db:/app/coxy.db \
  ghcr.io/coxy-proxy/coxy:latest
```

Coxy is now running at **http://localhost:3000**

#### Step 4 — Register your GitHub account

1. Open **http://localhost:3000** → go to **API Keys** → click **Login with GitHub**
2. A device code appears (e.g. `EB18-1E94`)
3. Go to **https://github.com/login/device** → enter the code → **Authorize**
   *(do this within ~15 minutes — codes expire)*
4. Return to http://localhost:3000 → your token appears in the list
5. Click the **⭐ star icon** to mark it as the **default token**

#### Step 5 — Verify Coxy works

```bash
curl -X POST http://localhost:3000/api/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer _" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"say hi"}]}'
```

A JSON response with GPT-4o's reply → ✅ Coxy is working.

### 3.3 Configure `.env`

```env
USE_COXY=true
USE_AZURE_OPENAI=false
USE_ANTHROPIC=false
USE_CUSTOM_LLM=false

COXY_BASE_URL=http://localhost:3000/api
COXY_MODEL=gpt-4o
COXY_API_KEY=_        # use _ when a default token is set in the Coxy UI
                      # OR: COXY_API_KEY=ghu_yourActualTokenHere
```

### 3.4 Available models (depends on your Copilot plan)

| Model | ID to use in `COXY_MODEL` | Notes |
|---|---|---|
| GPT-4o | `gpt-4o` | Recommended — best for tool calling |
| GPT-4.1 | `gpt-4.1` | Latest GPT-4 series |
| Claude 3.5 Sonnet | `claude-3.5-sonnet` | Via Copilot |
| o3-mini | `o3-mini` | Reasoning model |

### 3.5 After a system reboot

The database persists your token. No re-registration needed — just restart the container:

```bash
docker start coxy
```

### 3.6 Updating Coxy

```bash
docker stop coxy && docker rm coxy
docker pull ghcr.io/coxy-proxy/coxy:latest
# re-run the docker run command from Step 3
```

---

## 4. Option 2 — Azure OpenAI *(production recommended)*

**Best for:** Enterprise deployments, teams with Azure subscriptions, data residency requirements.
**Cost:** Azure consumption-based pricing.
**Requires:** Azure subscription, Azure OpenAI resource with a model deployed.

### 4.1 Create an Azure OpenAI resource

1. Sign in to the [Azure Portal](https://portal.azure.com)
2. Search for **Azure OpenAI** → **Create**
3. Choose your subscription, resource group, region, and name
4. Select a pricing tier (Standard S0 is typical)
5. After creation, go to the resource → **Keys and Endpoint**
6. Copy **Key 1** and the **Endpoint URL**

### 4.2 Deploy a model

1. In your Azure OpenAI resource → **Model deployments** → **Manage deployments**
2. This opens **Azure OpenAI Studio**
3. Click **Deploy model** → select `gpt-4o` (or another tool-capable model)
4. Give it a **deployment name** (e.g. `gpt-4o-prod`) — this is what you set in `.env`

> ⚠️ **Only models that support function/tool calling work with this agent.**
> Supported: `gpt-4o`, `gpt-4-turbo`, `gpt-4`, `gpt-35-turbo` (1106+).

### 4.3 Configure `.env`

```env
USE_COXY=false
USE_AZURE_OPENAI=true
USE_ANTHROPIC=false
USE_CUSTOM_LLM=false

AZURE_OPENAI_API_KEY=your-key-from-azure-portal
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-prod     # your deployment name (step 4.2)
AZURE_OPENAI_API_VERSION=2024-08-01-preview
```

### 4.4 Verify the connection

```bash
curl -X POST "https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT/chat/completions?api-version=2024-08-01-preview" \
  -H "api-key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"say hi"}]}'
```

### 4.5 Supported API versions

| Version | Status |
|---|---|
| `2024-08-01-preview` | ✅ Recommended |
| `2024-05-01-preview` | ✅ Works |
| `2024-02-01` | ✅ Stable |

Update `AZURE_OPENAI_API_VERSION` if a newer GA version is released.

---

## 5. Option 3 — Standard OpenAI *(ChatGPT)*

**Best for:** Teams with existing OpenAI API subscriptions.
**Cost:** Pay-per-token (see [openai.com/pricing](https://openai.com/pricing)).
**Requires:** OpenAI account with billing enabled.

### 5.1 Get an API key

1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Click **Create new secret key**
3. Copy it immediately — it is shown only once

### 5.2 Configure `.env`

```env
USE_COXY=false
USE_AZURE_OPENAI=false
USE_ANTHROPIC=false
USE_CUSTOM_LLM=false

OPENAI_API_KEY=sk-proj-...your-key-here...
OPENAI_MODEL=gpt-4o
```

*(When all USE_* flags are false, OpenAI is selected automatically — no extra flag needed.)*

### 5.3 Available models

| Model | `OPENAI_MODEL` value | Notes |
|---|---|---|
| GPT-4o | `gpt-4o` | ✅ Recommended — fastest + cheapest GPT-4 |
| GPT-4o mini | `gpt-4o-mini` | Cheaper, slightly less capable |
| GPT-4 Turbo | `gpt-4-turbo` | Older generation |
| GPT-4.1 | `gpt-4.1` | Latest generation |
| o3-mini | `o3-mini` | Reasoning model — slower but very accurate |

> ⚠️ **Do not use `gpt-3.5-turbo` for this agent.** It supports tool calling but is
> too weak to reliably reason about Terraform dependency chains.

### 5.4 Verify the API key

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer sk-proj-...your-key..."
```

A list of model IDs → ✅ key is valid.

---

## 6. Option 4 — Anthropic / Claude

**Best for:** Teams that prefer Anthropic's Claude models, or want best-in-class reasoning.
**Cost:** Pay-per-token (see [anthropic.com/pricing](https://www.anthropic.com/pricing)).
**Requires:** Anthropic account with API access.

### 6.1 Get an API key

1. Sign up or sign in at [console.anthropic.com](https://console.anthropic.com)
2. Go to **API Keys** → **Create Key**
3. Copy the key (starts with `sk-ant-api03-...`)
4. Add billing info if prompted — Anthropic requires it for API access

### 6.2 Install the SDK *(already done if you ran pip install)*

```bash
pip install anthropic
```

The `requirements.txt` includes `anthropic` — it is installed automatically.

### 6.3 Configure `.env`

```env
USE_COXY=false
USE_AZURE_OPENAI=false
USE_ANTHROPIC=true
USE_CUSTOM_LLM=false

ANTHROPIC_API_KEY=sk-ant-api03-...your-key-here...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### 6.4 Available models

Only models that support **tool use** work with this agent.

| Model | `ANTHROPIC_MODEL` value | Context | Best for |
|---|---|---|---|
| Claude 3.5 Sonnet | `claude-3-5-sonnet-20241022` | 200K | ✅ Recommended — fast, accurate, cheap |
| Claude 3.5 Haiku | `claude-3-5-haiku-20241022` | 200K | Fastest / cheapest Claude |
| Claude 3 Opus | `claude-3-opus-20240229` | 200K | Most capable, slower, expensive |
| Claude 3 Sonnet | `claude-3-sonnet-20240229` | 200K | Older generation |

### 6.5 How the Anthropic adapter works (developer note)

Anthropic's API differs from OpenAI in several ways — the `AnthropicWrapper` in
`src/llm/anthropic_wrapper.py` handles all of this transparently:

| Difference | OpenAI format | Anthropic format | Handled by wrapper |
|---|---|---|---|
| System prompt | `{"role":"system","content":"..."}` in messages | Separate `system=` parameter | ✅ extracted automatically |
| Tool schema | `"parameters": {...}` | `"input_schema": {...}` | ✅ converted automatically |
| Stop reason | `"stop"` / `"tool_calls"` | `"end_turn"` / `"tool_use"` | ✅ mapped automatically |
| Tool results | `{"role":"tool", "tool_call_id":"..."}` | `{"role":"user", "content":[{"type":"tool_result",...}]}` | ✅ converted automatically |
| Multiple tool results | Separate messages | Must be grouped in one user message | ✅ grouped automatically |

### 6.6 Verify the API key

```bash
curl https://api.anthropic.com/v1/models \
  -H "x-api-key: sk-ant-api03-...your-key..." \
  -H "anthropic-version: 2023-06-01"
```

A list of Claude models → ✅ key is valid.

---

## 7. Option 5 — Custom LLM *(Ollama, vLLM, LM Studio, any HTTP API)*

**Best for:** Running models locally (privacy), self-hosted models, non-standard providers,
or any HTTP API that doesn't fit the other options.
**Cost:** Depends on your setup (local = free).
**Requires:** An HTTP endpoint that accepts a POST request and returns a response.

### 7.1 Sub-option A — Ollama *(local, recommended for self-hosting)*

#### Install Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh

# Or download from: https://ollama.com/download
```

#### Pull a model

```bash
ollama pull llama3          # Meta Llama 3 8B (4.7GB)
ollama pull mistral         # Mistral 7B (4.1GB)
ollama pull llama3:70b      # Llama 3 70B (requires ~40GB RAM)
ollama pull qwen2.5:14b     # Qwen 2.5 14B — excellent tool calling
```

> ⚠️ **Tool calling support varies by model.** Not all models reliably use tools.
> Recommended models for tool calling with Ollama:
> `llama3.1`, `qwen2.5`, `mistral-nemo`, `command-r`

#### Start Ollama

```bash
ollama serve      # starts on http://localhost:11434
```

#### Configure `.env`

```env
USE_COXY=false
USE_AZURE_OPENAI=false
USE_ANTHROPIC=false
USE_CUSTOM_LLM=true

CUSTOM_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
CUSTOM_LLM_TOKEN=         # leave empty for Ollama
CUSTOM_LLM_MODEL=llama3.1
```

Ollama exposes an OpenAI-compatible endpoint — **no code changes needed in `custom_client.py`**.

---

### 7.2 Sub-option B — vLLM *(GPU server / cloud)*

vLLM is a high-throughput inference server for deploying open models on GPU.

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 8080 \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json
```

```env
USE_CUSTOM_LLM=true
CUSTOM_LLM_ENDPOINT=http://your-gpu-server:8080/v1/chat/completions
CUSTOM_LLM_TOKEN=your-vllm-token-if-set
CUSTOM_LLM_MODEL=meta-llama/Llama-3.1-8B-Instruct
```

---

### 7.3 Sub-option C — LM Studio *(GUI app, local)*

1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai)
2. Download a model in the app (search for `llama`, `qwen`, `mistral`, etc.)
3. Go to **Local Server** tab → click **Start Server**
4. Default endpoint: `http://localhost:1234/v1/chat/completions`

```env
USE_CUSTOM_LLM=true
CUSTOM_LLM_ENDPOINT=http://localhost:1234/v1/chat/completions
CUSTOM_LLM_TOKEN=lm-studio   # LM Studio accepts any non-empty value
CUSTOM_LLM_MODEL=lmstudio-community/Meta-Llama-3-8B-Instruct-GGUF
```

---

### 7.4 Sub-option D — Any other HTTP API

Edit `src/llm/custom_client.py` to implement your own `complete()` method.
The file contains two ready-made paths:

**Path A — OpenAI-compatible endpoint** (Ollama, vLLM, LM Studio, any proxy):
Your endpoint accepts the same JSON payload as OpenAI. No changes needed.

**Path B — Non-compatible endpoint** (proprietary API, plain text output):
Comment out Path A and uncomment Path B. You send plain messages, get plain text back.
The `_parse_text_for_tool_calls()` helper parses JSON blocks from text output.

```python
# Example: custom authentication header
self.headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {settings.custom_llm_token}",
    "X-My-Custom-Header": "value",
}

# Example: ChatGPT web via session token (unofficial)
self.headers = {
    "Content-Type": "application/json",
    "Cookie": f"__Secure-next-auth.session-token={settings.custom_llm_token}",
}
```

```env
USE_CUSTOM_LLM=true
CUSTOM_LLM_ENDPOINT=https://your-api.example.com/v1/chat
CUSTOM_LLM_TOKEN=your-session-token-or-api-key
CUSTOM_LLM_MODEL=your-model-name
```

---

## 8. Model recommendations by use case

| Use Case | Recommended Option | Model |
|---|---|---|
| **Local development / POC** | Coxy (Option 1) | `gpt-4o` via GitHub Copilot |
| **Enterprise production** | Azure OpenAI (Option 2) | `gpt-4o` |
| **Fastest iteration** | OpenAI (Option 3) | `gpt-4o-mini` |
| **Best reasoning / accuracy** | Anthropic (Option 4) | `claude-3-5-sonnet-20241022` |
| **Air-gapped / private** | Custom LLM (Option 5) | Ollama + `qwen2.5:14b` |
| **GPU server** | Custom LLM (Option 5) | vLLM + Llama 3.1 70B |
| **Budget-conscious** | Custom LLM (Option 5) | Ollama + `llama3.1` (free) |

> **Minimum model requirement:** The agent needs a model that supports native **function/tool calling**.
> Plain chat models without tool calling will not work correctly.

---

## 9. Developer guide — adding a new LLM backend

Follow the same pattern as `OpenAIWrapper` or `AnthropicWrapper`.

### Step 1 — Create `src/llm/my_provider_wrapper.py`

```python
from src.llm.base import (
    BaseLLMClient, AgentResponse, AgentChoice, AgentMessage, ToolCall, ToolFunction,
    LLMRateLimitError, LLMTimeoutError, LLMConnectionError, LLMStatusError,
)
from src.config.settings import settings

class MyProviderWrapper(BaseLLMClient):

    def __init__(self):
        # initialise your SDK client here
        pass

    def complete(self, model, messages, tools, tool_choice, temperature) -> AgentResponse:
        try:
            # call your provider's API here
            raw = ...
        except YourSDKRateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except YourSDKTimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except YourSDKConnectionError as e:
            raise LLMConnectionError(str(e)) from e
        except YourSDKStatusError as e:
            raise LLMStatusError(str(e), e.status_code) from e

        # translate raw response → AgentResponse
        return AgentResponse(choices=[
            AgentChoice(
                finish_reason="stop",           # or "tool_calls"
                message=AgentMessage(
                    role="assistant",
                    content=raw.text,           # or None if tool calls
                    tool_calls=[
                        ToolCall(id=..., function=ToolFunction(name=..., arguments=...))
                        for tc in raw.tool_calls
                    ],
                ),
            )
        ])
```

### Step 2 — Add settings to `src/config/settings.py`

```python
use_my_provider: bool = Field(False, alias="USE_MY_PROVIDER")
my_provider_api_key: str = Field("", alias="MY_PROVIDER_API_KEY")
my_provider_model: str = Field("my-default-model", alias="MY_PROVIDER_MODEL")
```

And add a branch to `model_name`:
```python
@property
def model_name(self) -> str:
    if self.use_custom_llm:
        return self.custom_llm_model
    if self.use_anthropic:
        return self.anthropic_model
    if self.use_my_provider:          # ← add here
        return self.my_provider_model
    ...
```

### Step 3 — Register in `src/agent/agent.py`

```python
def _get_client() -> BaseLLMClient:
    if settings.use_custom_llm:
        from src.llm.custom_client import CustomLLMClient
        return CustomLLMClient()
    if settings.use_anthropic:
        from src.llm.anthropic_wrapper import AnthropicWrapper
        return AnthropicWrapper()
    if settings.use_my_provider:            # ← add here
        from src.llm.my_provider_wrapper import MyProviderWrapper
        return MyProviderWrapper()
    return OpenAIWrapper()
```

### Step 4 — Add to `.env.example`

```env
USE_MY_PROVIDER=false
MY_PROVIDER_API_KEY=your-key-here
MY_PROVIDER_MODEL=my-default-model
```

**That's it.** `agent.py` and the rest of the app need no other changes.

---

## 10. Troubleshooting by provider

### Coxy

| Symptom | Fix |
|---|---|
| `"Invalid authorization header: Bearer _"` | Go to http://localhost:3000/api-keys → click ⭐ next to your token to set it as default |
| `"Too many requests"` device code error | Container restarted without persistent DB. Re-register: http://localhost:3000 → Login with GitHub |
| Container won't start | Check port 3000 is free: `lsof -i :3000`. Try `docker ps -a` then `docker rm coxy` |
| Token expired after months | Repeat the Login with GitHub flow — Coxy tokens expire periodically |

### Azure OpenAI

| Symptom | Fix |
|---|---|
| `AuthenticationError` | Wrong API key. Copy Key 1 from Azure Portal → Keys and Endpoint |
| `ResourceNotFound` | Wrong endpoint URL or deployment name. Check Azure Portal → Model deployments |
| `DeploymentNotFound` | `AZURE_OPENAI_DEPLOYMENT_NAME` must match your deployment name exactly (case-sensitive) |
| `InvalidApiVersion` | Use `2024-08-01-preview` or check current supported versions |
| `RateLimitError` | Your Azure quota is exhausted. Check Azure Portal → Quotas |

### OpenAI

| Symptom | Fix |
|---|---|
| `AuthenticationError` | Invalid API key. Regenerate at platform.openai.com/api-keys |
| `RateLimitError` | Check your rate limits and billing at platform.openai.com/usage |
| `model_not_found` | Model name is wrong. Check `OPENAI_MODEL` spelling |
| `insufficient_quota` | Add a payment method or increase limits at platform.openai.com/account/billing |

### Anthropic

| Symptom | Fix |
|---|---|
| `AuthenticationError` | API key is wrong or expired. Regenerate at console.anthropic.com/api-keys |
| `RateLimitError` | Check usage at console.anthropic.com. Claude rate limits are per-minute and per-day |
| `overloaded_error` | Anthropic API is under heavy load. Retry after a moment |
| Tool call loop / agent not stopping | Switch to `claude-3-5-sonnet-20241022` — older Claude 3 models have weaker tool-use reliability |

### Custom LLM / Ollama

| Symptom | Fix |
|---|---|
| `ConnectionError: Cannot reach the AI service` | Ollama not running. Run `ollama serve` then verify: `curl http://localhost:11434/api/tags` |
| Model doesn't use tools | Switch to a model with better tool support: `qwen2.5:14b` or `llama3.1` |
| `model not found` | Run `ollama pull <model-name>` to download first |
| Very slow responses | Run `ollama list` to see loaded models. A 70B model needs ~40GB RAM |
| Agent gives wrong/hallucinated plans | Model too small for the task. Try at least a 13B parameter model |

### General

| Symptom | Fix |
|---|---|
| `TypeError: unexpected keyword argument 'proxies'` | httpx/openai version mismatch: `pip install "httpx>=0.27,<0.28" "openai==1.51.0"` |
| Agent returns 500 error | Check server terminal output for the actual Python traceback |
| Port 8000 already in use | `pkill -f "python main.py"` then restart |
| `DEBUG=release` validation error | Your shell has an env var overriding `.env`. Set `DEBUG=true` in `.env` |
