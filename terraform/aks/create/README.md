# AKS — create

## What it does
Creates an Azure Kubernetes Service (AKS) cluster with:
- Azure CNI networking (pods get VNet IPs)
- Managed identity authentication (no service principals)
- Azure AD integration with Kubernetes RBAC
- Container Insights monitoring via Log Analytics
- Key Vault Secrets Provider addon

## When to use
When the workload requires running containerised applications at scale with Kubernetes orchestration.

## Important notes
- Production clusters must have `private_cluster_enabled = true` (API server behind private endpoint)
- Azure AD integration is mandatory — no local accounts
- Autoscaler is enabled by default; set min/max node counts appropriately
- System node pool uses dedicated nodes — do not schedule application workloads on it

## Dependencies (all must be deployed first)
- **Resource Group** (`resource_group/create`) — referenced via `data "azurerm_resource_group"`
- **Virtual Network** (`virtual_network/create`) — referenced via `data "azurerm_virtual_network"` and `data "azurerm_subnet"`
- **AKS common resources** (`aks/create_common_resource`) — referenced via `data "azurerm_container_registry"`, `data "azurerm_log_analytics_workspace"`, `data "azurerm_user_assigned_identity"`
- **Key Vault** (`key_vault/create`) — referenced via `data "azurerm_key_vault"` (for secrets provider addon)

## Outputs
- `cluster_id` — AKS cluster resource ID
- `cluster_name` — cluster name
- `kube_config` — kubeconfig for kubectl access (sensitive)
- `node_resource_group` — the MC_ resource group auto-created by AKS
- `oidc_issuer_url` — for workload identity federation
