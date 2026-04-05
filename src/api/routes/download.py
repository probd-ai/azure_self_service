"""
api/routes/download.py — Bundle download endpoint

Serves zip bundles created by bundle_deployment_plan() tool.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from src.tools.bundle_tools import get_bundle_path

router = APIRouter()


@router.get("/download/{bundle_id}")
def download_bundle(bundle_id: str):
    """
    Download a deployment bundle zip created by the AI agent.

    The bundle contains:
    - All required .tf template files (policy-compliant, unmodified)
    - A terraform.tfvars file per step pre-filled with the customer's values
    - A README.txt with ordered deployment instructions and commands
    """
    # Sanitise bundle_id — only allow hex chars to prevent path traversal
    if not bundle_id.isalnum() or len(bundle_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid bundle ID.")

    zip_path = get_bundle_path(bundle_id)
    if not zip_path:
        raise HTTPException(
            status_code=404,
            detail=f"Bundle '{bundle_id}' not found. Bundles are ephemeral — re-run the deployment plan to generate a new one."
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"azure-deployment-bundle-{bundle_id}.zip",
    )
