# AKS — create_common_resource

## What it does
Creates the prerequisite resources needed **before** the AKS cluster itself can be deployed:
- **Azure Container Registry (ACR)** — stores container images for the cluster
- **Log Analytics Workspace** — receives Container Insights monitoring data from AKS
- **User-Assigned Managed Identity** — used by the AKS cluster to interact with ACR and Key Vault

## When to use
Deploy this **before** `aks/create`. The AKS cluster template references the ACR, Log Analytics Workspace, and Managed Identity by name using `data {}` blocks.

## Important notes
- ACR name must be globally unique, 5-50 alphanumeric characters, no hyphens
- Log Analytics Workspace retention defaults to 30 days (minimum for compliance)
- Naming convention: `acr<project><environment>`, `law-<project>-<environment>`

## Dependencies
- **Resource Group** (`resource_group/create`) — referenced via `data "azurerm_resource_group"`

## Outputs
- `acr_id` — ACR resource ID
- `acr_login_server` — ACR login URL (e.g. myacr.azurecr.io)
- `law_id` — Log Analytics Workspace resource ID
- `law_workspace_id` — Log Analytics Workspace GUID (used by AKS monitoring addon)
- `managed_identity_id` — User-assigned managed identity resource ID
- `managed_identity_principal_id` — Principal ID (for RBAC assignments)
- `managed_identity_client_id` — Client ID (for workload identity federation)
