# ── App Service Plan ──────────────────────────────────────────────────────────

output "app_service_plan_id" {
  description = "Resource ID of the shared App Service Plan"
  value       = azurerm_service_plan.logic_shared.id
}

output "app_service_plan_name" {
  description = "Name of the shared App Service Plan — pass to logic_app/create as app_service_plan_name"
  value       = azurerm_service_plan.logic_shared.name
}

# ── Storage Account ───────────────────────────────────────────────────────────

output "storage_account_id" {
  description = "Resource ID of the shared storage account"
  value       = azurerm_storage_account.logic_state.id
}

output "storage_account_name" {
  description = "Name of the shared storage account — pass to logic_app/create as storage_account_name"
  value       = azurerm_storage_account.logic_state.name
}

output "storage_primary_connection_string" {
  description = "Primary connection string of the shared storage account (sensitive)"
  value       = azurerm_storage_account.logic_state.primary_connection_string
  sensitive   = true
}

# ── Log Analytics Workspace ───────────────────────────────────────────────────

output "log_analytics_workspace_id" {
  description = "Resource ID of the shared Log Analytics Workspace"
  value       = azurerm_log_analytics_workspace.logic_law.id
}

output "log_analytics_workspace_name" {
  description = "Name of the shared Log Analytics Workspace — pass to logic_app/create"
  value       = azurerm_log_analytics_workspace.logic_law.name
}

# ── Managed Identity ──────────────────────────────────────────────────────────

output "managed_identity_id" {
  description = "Full resource ID of the shared User-Assigned Managed Identity"
  value       = azurerm_user_assigned_identity.logic_identity.id
}

output "managed_identity_name" {
  description = "Name of the shared Managed Identity — pass to logic_app/create"
  value       = azurerm_user_assigned_identity.logic_identity.name
}

output "managed_identity_principal_id" {
  description = "Principal ID (object ID) of the Managed Identity — used for role assignments"
  value       = azurerm_user_assigned_identity.logic_identity.principal_id
}

output "managed_identity_client_id" {
  description = "Client ID of the Managed Identity — used in AzureWebJobsStorage__clientId app setting"
  value       = azurerm_user_assigned_identity.logic_identity.client_id
}

# ── Service Bus API Connection (azapi) ────────────────────────────────────────

output "servicebus_connection_id" {
  description = "Resource ID of the shared Service Bus API connection — pass to logic_app/create as servicebus_connection_id"
  value       = azapi_resource.servicebus_connection.id
}

output "servicebus_connection_name" {
  description = "Name of the shared Service Bus API connection"
  value       = azapi_resource.servicebus_connection.name
}

output "servicebus_managed_api_capabilities" {
  description = "Capability list of the Service Bus managed API (from azapi data source)"
  value       = jsondecode(data.azapi_resource.servicebus_managed_api.output).properties.capabilities
}
