output "acr_id" {
  value       = azurerm_container_registry.acr.id
  description = "Azure resource ID of the Container Registry"
}

output "acr_login_server" {
  value       = azurerm_container_registry.acr.login_server
  description = "ACR login server URL (e.g. myacr.azurecr.io)"
}

output "law_id" {
  value       = azurerm_log_analytics_workspace.law.id
  description = "Azure resource ID of the Log Analytics Workspace"
}

output "law_workspace_id" {
  value       = azurerm_log_analytics_workspace.law.workspace_id
  description = "Log Analytics Workspace GUID — used by AKS monitoring addon"
}

output "managed_identity_id" {
  value       = azurerm_user_assigned_identity.aks_identity.id
  description = "Resource ID of the user-assigned managed identity"
}

output "managed_identity_principal_id" {
  value       = azurerm_user_assigned_identity.aks_identity.principal_id
  description = "Principal ID — used for RBAC assignments"
}

output "managed_identity_client_id" {
  value       = azurerm_user_assigned_identity.aks_identity.client_id
  description = "Client ID — used for workload identity federation"
}
