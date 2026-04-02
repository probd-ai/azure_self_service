"""
api/routes/credentials.py — Credential management endpoints.

SECURITY PRINCIPLES
───────────────────
• These endpoints bypass the AI entirely — credentials go directly to the vault.
• Response bodies NEVER contain secret values — only masked hints and the credential_id.
• The credential_id is a stable UUID the frontend stores in localStorage and sends
  with every chat request.  It acts as a lightweight "user ID" for Phase 2.
• When Azure AD SSO is added (Phase 4), replace credential_id lookup with the
  Azure AD object ID from the JWT token.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from src.credentials.models import CredentialRegistration, CredentialStatus
from src.credentials.store import get_vault

router = APIRouter()


@router.post("/credentials", response_model=CredentialStatus, status_code=201)
def register_credentials(body: CredentialRegistration, credential_id: str | None = None):
    """
    Register or update a user's Azure credentials.

    - First call (no credential_id): creates a new vault entry, returns a fresh credential_id.
    - Subsequent calls (with credential_id in query param): updates the existing entry.

    The frontend stores the returned credential_id in localStorage.
    Secret values are NEVER returned — only masked hints.
    """
    vault = get_vault()
    status = vault.register(body, credential_id=credential_id)
    logger.info(f"Credentials registered for {status.credential_id}")
    return status


@router.get("/credentials/{credential_id}", response_model=CredentialStatus)
def get_credential_status(credential_id: str):
    """
    Return masked status of stored credentials (no secret values).
    Used by the UI to show ✓ / ✗ next to each field.
    """
    vault = get_vault()
    status = vault.get_status(credential_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Credentials not found. Please register first.")
    return status


@router.delete("/credentials/{credential_id}", status_code=204)
def delete_credentials(credential_id: str):
    """Delete stored credentials and their vault file."""
    vault = get_vault()
    deleted = vault.delete(credential_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credentials not found.")
