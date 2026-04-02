"""
api/routes/deploy.py — Deployment trigger endpoints.

Flow
────
1. Frontend sends POST /api/deploy with:
     { session_id, template_path, credential_id }
2. Backend:
   a. Loads the session → gets AI-collected non-sensitive vars
   b. Loads encrypted credentials from vault using credential_id
   c. Creates an isolated workspace (copy of template)
   d. Injects ALL variables into terraform.tfvars (vault secrets + AI vars merged)
   e. Runs terraform plan
   f. Returns plan output to UI for user approval
3. Frontend shows plan, user clicks Approve
4. POST /api/deploy/{job_id}/approve → runs terraform apply

Sensitive values NEVER appear in:
  • API request/response bodies
  • Log lines (they're redacted in VariableInjector)
  • The AI conversation
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger
from pydantic import BaseModel

from src.agent.conversation import conversation_manager
from src.config.settings import settings
from src.credentials.store import get_vault
from src.deployment.runners.base import RunResult, RunStatus
from src.deployment.runners.factory import create_runner
from src.deployment.variable_injector import VariableInjector
from src.deployment.workspace import get_workspace_manager

router = APIRouter()

# In-memory job store (swap for Redis / DB in Phase 3)
_jobs: dict[str, dict] = {}

injector = VariableInjector()


class DeployRequest(BaseModel):
    session_id: str
    template_path: str   # e.g. "terraform/virtual_network/create"
    credential_id: str


class DeployResponse(BaseModel):
    job_id: str
    status: str
    plan_output: str = ""
    error: str = ""
    message: str = ""


class ApproveResponse(BaseModel):
    job_id: str
    status: str
    output: str = ""
    error: str = ""


# ── Helper ────────────────────────────────────────────────────────────────────

def _resolve_template_path(template_path: str) -> Path:
    """Resolve and validate the template path against the allowed base directory."""
    base = settings.tf_base_path.resolve()
    resolved = (base.parent / template_path).resolve()
    # Security: ensure the path is inside the terraform/ base directory
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid template path.")
    if not resolved.exists() or not (resolved / "variables.tf").exists():
        raise HTTPException(
            status_code=404,
            detail=f"Template not found or missing variables.tf: {template_path}"
        )
    return resolved


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/deploy", response_model=DeployResponse, status_code=202)
def start_plan(body: DeployRequest):
    """
    Step 1 of 2: Run terraform plan.
    Returns the plan output for user review before apply.
    """
    # Load session → get AI-collected vars
    session = conversation_manager.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found. Start a conversation first.")

    collected_vars = session.collected_vars

    # Load credentials from vault (never passed to AI)
    vault = get_vault()
    creds = vault.get_credentials(body.credential_id)
    if creds is None:
        raise HTTPException(
            status_code=400,
            detail="Azure credentials not found. Please register your credentials in Settings first."
        )

    # Resolve template
    template_path = _resolve_template_path(body.template_path)

    # Create isolated workspace
    wm = get_workspace_manager()
    workspace = wm.create(session_id=body.session_id, template_path=template_path)

    # Inject variables (vault secrets + AI vars → terraform.tfvars)
    try:
        injector.inject(
            workspace_dir=workspace.workspace_dir,
            template_path=template_path,
            creds=creds,
            collected_vars=collected_vars,
        )
    except (ValueError, FileNotFoundError) as exc:
        wm.delete(body.session_id, workspace.job_id)
        raise HTTPException(status_code=422, detail=str(exc))

    # Run terraform plan (synchronous for Phase 2 — use Celery for Phase 3)
    runner = create_runner(settings.tf_runner_type)
    result: RunResult = runner.plan(workspace.workspace_dir, workspace.job_id)

    # Store job state for the approve step
    _jobs[workspace.job_id] = {
        "session_id": body.session_id,
        "workspace_dir": str(workspace.workspace_dir),
        "status": result.status.value,
        "plan_output": result.plan_output,
    }

    if result.status == RunStatus.FAILED:
        return DeployResponse(
            job_id=workspace.job_id,
            status="failed",
            error=f"Plan failed: {result.stderr or result.error}",
        )

    return DeployResponse(
        job_id=workspace.job_id,
        status="plan_ready",
        plan_output=result.plan_output,
        message="Review the plan above, then click Approve to deploy.",
    )


@router.post("/deploy/{job_id}/approve", response_model=ApproveResponse)
def approve_and_apply(job_id: str):
    """
    Step 2 of 2: Apply the previously reviewed plan.
    Only callable after a successful /api/deploy (plan_ready status).
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    if job["status"] != "plan_ready":
        raise HTTPException(status_code=409, detail=f"Job is in state '{job['status']}', not 'plan_ready'.")

    workspace_dir = Path(job["workspace_dir"])
    runner = create_runner(settings.tf_runner_type)
    result: RunResult = runner.apply(workspace_dir, job_id)

    # Update job state
    job["status"] = result.status.value

    if result.status == RunStatus.FAILED:
        return ApproveResponse(
            job_id=job_id,
            status="failed",
            error=f"Apply failed: {result.stderr or result.error}",
        )

    return ApproveResponse(
        job_id=job_id,
        status="succeeded",
        output=result.stdout,
    )


@router.get("/deploy/{job_id}", response_model=DeployResponse)
def get_job_status(job_id: str):
    """Get the current status of a deployment job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return DeployResponse(
        job_id=job_id,
        status=job["status"],
        plan_output=job.get("plan_output", ""),
    )


@router.get("/deploy/{session_id}/readiness")
def check_readiness(session_id: str, template_path: str, credential_id: str):
    """
    Check if all required variables are collected for a given template.
    The AI can call this indirectly — the UI polls it to enable/disable Deploy button.
    Returns which vars are still missing so the AI knows what to ask next.
    """
    session = conversation_manager.get(session_id)
    collected_vars = session.collected_vars if session else {}

    vault = get_vault()
    creds = vault.get_credentials(credential_id) if credential_id else None

    try:
        tmpl_path = _resolve_template_path(template_path)
    except HTTPException as exc:
        return {"ready": False, "error": exc.detail}

    result = injector.check_readiness(
        template_path=tmpl_path,
        creds=creds,
        collected_vars=collected_vars,
    )
    return result
