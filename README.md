# Azure Self-Service AI Agent

An AI-driven self-service platform that helps customers understand, plan, and deploy Azure infrastructure using company-approved, policy-compliant Terraform templates.

Instead of digging through documentation or raising tickets, a customer simply **describes what they want** in plain English. The AI agent reads the actual Terraform templates, figures out dependencies, and produces a complete step-by-step deployment plan — including the exact Terraform commands and variables needed.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Quick Start](#quick-start)
   - [Step 1 — Clone the repo](#step-1--clone-the-repo)
   - [Step 2 — Start the LLM (Coxy / GitHub Copilot)](#step-2--start-the-llm-coxy--github-copilot-free)
   - [Step 3 — Configure the project](#step-3--configure-the-project)
   - [Step 4 — Install Python dependencies](#step-4--install-python-dependencies)
   - [Step 5 — Run the agent](#step-5--run-the-agent)
   - [Step 6 — Test it](#step-6--test-it)
5. [LLM Provider Options](#llm-provider-options)
6. [API Reference](#api-reference)
7. [Terraform Templates — The Source of Truth](#terraform-templates--the-source-of-truth)
8. [Adding a New Azure Service](#adding-a-new-azure-service)
9. [Roadmap](#roadmap)
10. [Troubleshooting](#troubleshooting)

---

## How It Works

```
Customer: "I want to deploy an AKS cluster"
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI Agent (GPT-4o)                        │
│                                                             │
│  1. list_directory("terraform/")                            │
│     → discovers: aks/, vnet/, resource_group/, kv/ ...      │
│                                                             │
│  2. list_directory("terraform/aks/")                        │
│     → discovers: create/, create_common_resource/           │
│                                                             │
│  3. read_file("terraform/aks/create/README.md")             │
│     → understands what AKS does, what it needs              │
│                                                             │
│  4. read_file("terraform/aks/create/main.tf")               │
│     → finds data{} blocks → infers dependencies:            │
│       azurerm_resource_group, azurerm_virtual_network,      │
│       azurerm_key_vault, azurerm_log_analytics_workspace    │
│                                                             │
│  5. read_file("terraform/aks/create/variables.tf")          │
│     → knows exactly what inputs customer must provide       │
│                                                             │
│  6. Repeats steps 3-5 for every dependency found            │
│                                                             │
│  → Builds full dependency tree                              │
│  → Generates ordered deployment plan                        │
│  → Returns plan with TF commands + variables                │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
Customer gets: deployment order, required variables,
               terraform commands, and relevant code snippets
```

**Key design decision:** The agent uses just **2 tools** — `list_directory` and `read_file`. It reads your actual Terraform files directly. There is no hardcoded catalog, no separate policy database — the `terraform/` folder is the single source of truth. Adding a new service is as simple as adding a new folder.

---

## Prerequisites

Before you start, make sure you have the following:

| Tool | Version | How to check | Install |
|---|---|---|---|
| **Python** | 3.10 or higher | `python3 --version` | [python.org](https://python.org) |
| **Docker** | Any recent version | `docker --version` | [docs.docker.com](https://docs.docker.com/get-docker/) |
| **Git** | Any version | `git --version` | [git-scm.com](https://git-scm.com) |
| **GitHub Copilot** | Active subscription | — | [github.com/features/copilot](https://github.com/features/copilot) |

> **No Azure subscription needed for Phase 1.** The agent only reads Terraform templates and generates plans — it does not deploy anything yet.

---

## Project Structure

```
Azure_self_service/
│
├── main.py                          ← Entry point — run this to start everything
├── requirements.txt                 ← Python dependencies
├── .env.example                     ← Config template — copy this to .env
├── .env                             ← Your actual secrets/config (never commit this)
├── .gitignore
├── README.md
│
├── src/                             ← All application source code
│   │
│   ├── config/
│   │   └── settings.py              ← Reads .env and exposes typed settings to the app
│   │
│   ├── tools/
│   │   ├── fs_tools.py              ← list_directory() + read_file() — the 2 agent tools
│   │   └── tf_tools.py              ← terraform plan/apply stubs (Phase 2, not active yet)
│   │
│   ├── mcp/
│   │   └── server.py                ← MCP protocol wrapper (for external MCP integrations)
│   │
│   ├── agent/
│   │   ├── agent.py                 ← The agentic loop: LLM calls tools repeatedly until done
│   │   ├── prompts.py               ← System prompt — the "brain" instructions for the LLM
│   │   └── conversation.py          ← Session store for multi-turn conversations
│   │
│   ├── api/
│   │   ├── main.py                  ← FastAPI app + CORS config
│   │   └── routes/
│   │       └── chat.py              ← POST /api/chat  |  DELETE /api/sessions/{id}
│   │
│   └── models/
│       └── schemas.py               ← Request/response data models (Pydantic)
│
├── terraform/                       ← SOURCE OF TRUTH — agent reads these files directly
│   ├── resource_group/create/
│   ├── virtual_network/create/
│   ├── virtual_network/create_common_resource/
│   ├── storage_account/create/
│   ├── key_vault/create/
│   ├── aks/create/
│   └── aks/create_common_resource/
│
└── .coxy/
    └── coxy.db                      ← Persistent SQLite DB storing your GitHub token for Coxy
```

---

## Quick Start

### Step 1 — Clone the repo

```bash
git clone <repo-url>
cd Azure_self_service
```

---

### Step 2 — Start the LLM (Coxy / GitHub Copilot) *(free)*

**What is Coxy?** Coxy is a tiny local Docker container that acts as a proxy. It exposes your existing **GitHub Copilot subscription** as an OpenAI-compatible API. This means you get GPT-4o for free (within your Copilot quota) with no Azure or OpenAI billing.

#### 2a — Create a persistent database (one time only)

```bash
mkdir -p .coxy && touch .coxy/coxy.db
```

This file stores your GitHub token so you don't need to re-register every time you restart.

#### 2b — Initialise the database schema (one time only)

```bash
docker run --rm \
  -e DATABASE_URL="file:/app/coxy.db" \
  -v $(pwd)/.coxy/coxy.db:/app/coxy.db \
  ghcr.io/coxy-proxy/coxy:latest --provision
```

Expected output: `The database is already in sync with the Prisma schema.` ✅

#### 2c — Start Coxy in the background

```bash
docker run -d \
  --name coxy \
  -p 3000:3000 \
  -e DATABASE_URL="file:/app/coxy.db" \
  -v $(pwd)/.coxy/coxy.db:/app/coxy.db \
  ghcr.io/coxy-proxy/coxy:latest
```

Coxy is now running at **http://localhost:3000**

#### 2d — Register your GitHub account

1. Open **http://localhost:3000** in your browser
2. Go to the **API Keys** page
3. Click **"Login with GitHub"**
4. A code will appear — something like `EB18-1E94`
5. In a new tab, go to **https://github.com/login/device**
6. Enter the code and click **Authorize** — do this quickly (codes expire in ~15 min)
7. Come back to http://localhost:3000 — your token will appear in the list
8. Click the **⭐ star icon** next to your token to mark it as the **default**

#### 2e — Verify Coxy works

```bash
curl -X POST http://localhost:3000/api/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer _" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"say hi in 3 words"}]}'
```

If you see a JSON response with GPT-4o's reply — Coxy is working. ✅

> **After the first setup:** To restart Coxy after a reboot, just run `docker start coxy`. Your token is saved in `.coxy/coxy.db` — no re-registration needed.

---

### Step 3 — Configure the project

```bash
cp .env.example .env
```

Open `.env` and set your `COXY_API_KEY`. If you set a default token in the Coxy UI, use `_`. Otherwise paste your actual token (visible in the Coxy API Keys page, starts with `ghu_`):

```env
USE_COXY=true
USE_AZURE_OPENAI=false

COXY_BASE_URL=http://localhost:3000/api
COXY_MODEL=gpt-4o
COXY_API_KEY=_                        # Use _ if default token is set in Coxy UI
                                      # OR: COXY_API_KEY=ghu_yourActualTokenHere

API_HOST=0.0.0.0
API_PORT=8000
DEBUG=true

TF_TEMPLATES_BASE_PATH=./terraform
```

---

### Step 4 — Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### Step 5 — Run the agent

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

### Step 6 — Test it

#### Easiest — Swagger UI

Open **http://localhost:8000/docs** in your browser → click `POST /api/chat` → **Try it out** → type a message → **Execute**.

#### Via curl

```bash
# Ask what services are available
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what azure services can I deploy?"}' | python3 -m json.tool
```

```bash
# Ask for a full deployment plan (use the session_id from the previous response)
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to deploy AKS. Give me a complete step-by-step deployment plan.",
    "session_id": "paste-session-id-here"
  }' | python3 -m json.tool
```

---

## LLM Provider Options

Five backends are supported. Switch any time by editing `.env` and restarting `python main.py`.

> 📖 **Full setup instructions, model lists, and troubleshooting for every provider:**
> see **[LLM_SETUP_GUIDE.md](LLM_SETUP_GUIDE.md)**

| # | Provider | Flag | Best for |
|---|---|---|---|
| 1 | **Coxy / GitHub Copilot** | `USE_COXY=true` | Free POC (needs Docker + Copilot sub) |
| 2 | **Azure OpenAI** | `USE_AZURE_OPENAI=true` | Enterprise / production |
| 3 | **Standard OpenAI** | *(default — no flag needed)* | Existing OpenAI API key |
| 4 | **Anthropic (Claude)** | `USE_ANTHROPIC=true` | Best reasoning, 200K context |
| 5 | **Custom HTTP LLM** | `USE_CUSTOM_LLM=true` | Ollama, vLLM, LM Studio, any API |

### Quick `.env` examples

### Option A — Coxy / GitHub Copilot *(POC / free)*

Requires: Docker + active GitHub Copilot subscription

```env
USE_COXY=true
USE_AZURE_OPENAI=false
COXY_BASE_URL=http://localhost:3000/api
COXY_MODEL=gpt-4o
COXY_API_KEY=_
```

Available models (depends on your Copilot plan): `gpt-4o`, `gpt-4.1`, `claude-3.5-sonnet`, `o3-mini`

### Option B — Azure OpenAI *(production recommended)*

```env
USE_COXY=false
USE_AZURE_OPENAI=true
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-08-01-preview
```

### Option C — Standard OpenAI

```env
USE_COXY=false
USE_AZURE_OPENAI=false
OPENAI_API_KEY=your-key-here
OPENAI_MODEL=gpt-4o
```

### Option D — Anthropic (Claude)

```env
USE_ANTHROPIC=true
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
```

### Option E — Custom LLM (Ollama example)

```bash
ollama pull llama3.1   # download the model
ollama serve           # start on http://localhost:11434
```

```env
USE_CUSTOM_LLM=true
CUSTOM_LLM_ENDPOINT=http://localhost:11434/v1/chat/completions
CUSTOM_LLM_MODEL=llama3.1
```

---

## API Reference

### `GET /health`

Confirms the server is running.

```bash
curl http://localhost:8000/health
# → {"status": "ok"}
```

---

### `POST /api/chat`

Send a message to the AI agent.

**Request body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `message` | string | ✅ | The customer's question or request in plain English |
| `session_id` | string | ❌ | Pass the `session_id` from a previous response to continue the same conversation |

**Start a new conversation:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to deploy a storage account. What do I need?"}'
```

**Continue the conversation:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Do I need a VNet for private access?",
    "session_id": "abc-123-def-456"
  }'
```

**Response:**
```json
{
  "reply": "Yes, if you want private access to the Storage Account you will need a VNet...",
  "session_id": "abc-123-def-456"
}
```

---

### `DELETE /api/sessions/{session_id}`

Clear a conversation and start fresh.

```bash
curl -X DELETE http://localhost:8000/api/sessions/abc-123-def-456
```

---

## Terraform Templates — The Source of Truth

The agent reads the `terraform/` folder directly. Every service follows this layout:

```
terraform/<service_name>/
│
├── create/                    ← Deploys the main resource
│   ├── README.md              ← MOST IMPORTANT: agent reads this to understand the service
│   ├── main.tf                ← HCL code; data{} blocks here reveal dependencies
│   ├── variables.tf           ← Inputs the customer must supply
│   ├── outputs.tf             ← Values this template exposes to other templates
│   └── provider.tf            ← Azure provider config
│
└── create_common_resource/    ← (if present) prerequisite resources
    ├── README.md              ← Must be deployed BEFORE create/
    ├── main.tf
    ├── variables.tf
    ├── outputs.tf
    └── provider.tf
```

**How the agent finds dependencies:** It reads `data {}` blocks in `main.tf`. For example:

```hcl
# In terraform/aks/create/main.tf
data "azurerm_resource_group" "this" { ... }       # → depends on resource_group/create
data "azurerm_virtual_network" "vnet" { ... }      # → depends on virtual_network/create
data "azurerm_key_vault" "kv" { ... }              # → depends on key_vault/create
```

The agent sees these, reads each dependency's templates in turn, and builds the correct deployment order automatically.

**Services available today:**

| Service | Path | Templates |
|---|---|---|
| Resource Group | `terraform/resource_group/` | `create/` |
| Virtual Network | `terraform/virtual_network/` | `create/`, `create_common_resource/` |
| Storage Account | `terraform/storage_account/` | `create/` |
| Key Vault | `terraform/key_vault/` | `create/` |
| AKS | `terraform/aks/` | `create/`, `create_common_resource/` |

---

## Adding a New Azure Service

**No code changes required.** Just add files and the agent will discover the service automatically.

```bash
# 1. Create the folder
mkdir -p terraform/my_new_service/create

# 2. Add Terraform files
touch terraform/my_new_service/create/{main.tf,variables.tf,outputs.tf,provider.tf,README.md}
```

**Write a good `README.md`** — this is what the agent reads to understand the service:

```markdown
# My New Service

## What it does
[Describe what this service does and what Azure resource it creates]

## When to use
[Describe the scenarios where a customer would need this]

## Important notes
[Company policy constraints, naming conventions, enforced settings]

## Dependencies
- **Resource Group** (resource_group/create) — referenced via `data "azurerm_resource_group"`
- [any other deps]

## Outputs
- `output_name` — description
```

If the service has prerequisites (e.g. an identity or log workspace that must exist first), add a `create_common_resource/` folder with the same files.

---

## Roadmap

| Phase | Feature | Status |
|---|---|---|
| **1** | Agent explores TF templates and builds deployment plans | ✅ Done |
| **1** | Multi-turn conversations with session context | ✅ Done |
| **1** | Coxy (GitHub Copilot), Azure OpenAI, and OpenAI support | ✅ Done |
| **2** | Collect variable values from customer interactively | 🔜 Planned |
| **2** | `terraform plan` — show dry run output before applying | 🔜 Planned |
| **2** | Customer approval gate — confirm each step | 🔜 Planned |
| **2** | `terraform apply` — actual provisioning after approval | 🔜 Planned |
| **2** | Deployment status polling and progress updates | 🔜 Planned |

---

## Troubleshooting

### Coxy: "Too many requests have been made in the same timeframe"

GitHub rate-limited the device code. This happens when the container restarted without a persistent DB and kept polling an old/expired code.

**Fix:** Go to http://localhost:3000/api-keys → **Login with GitHub** → get a fresh code → enter it immediately at https://github.com/login/device.

---

### Coxy: "Invalid authorization header: Bearer _"

The dummy key `_` only works when a **default token** is set in the Coxy UI.

**Fix:** Go to http://localhost:3000/api-keys → click the **⭐ star icon** next to your token to make it the default. Or set the real token directly: `COXY_API_KEY=ghu_yourtoken`.

---

### Agent: `TypeError: unexpected keyword argument 'proxies'`

Version mismatch between `openai` and `httpx` libraries.

**Fix:**
```bash
pip install "httpx>=0.27,<0.28" "openai==1.51.0"
```

---

### Agent returns 500 Internal Server Error

Check what the server logged:
```bash
# If you started with output redirected:
tail -30 /tmp/agent.log

# If running in foreground, check the terminal output directly
```

---

### Port 8000 already in use

```bash
pkill -f "python main.py"
python main.py
```

---

### Restart everything after a system reboot

```bash
# Restart Coxy (token is saved in .coxy/coxy.db — no re-registration needed)
docker start coxy

# Restart the agent
cd Azure_self_service
source .venv/bin/activate
python main.py
```
