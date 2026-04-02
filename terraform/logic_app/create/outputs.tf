# ── Logic App Standard (azapi) ────────────────────────────────────────────────

output "logic_app_id" {
  description = "Resource ID of the Logic App Standard instance"
  value       = azapi_resource.logic_app.id
}

output "logic_app_name" {
  description = "Name of the Logic App Standard instance"
  value       = azapi_resource.logic_app.name
}

output "logic_app_default_hostname" {
  description = "Default hostname for triggering workflows via HTTP (e.g. myapp.azurewebsites.net)"
  value       = jsondecode(azapi_resource.logic_app.output).properties.defaultHostName
}

output "logic_app_outbound_ips" {
  description = "Comma-separated list of outbound IP addresses used by this Logic App"
  value       = jsondecode(azapi_resource.logic_app.output).properties.outboundIpAddresses
}

# ── Workflow (azapi) ──────────────────────────────────────────────────────────

output "workflow_id" {
  description = "Resource ID of the workflow inside the Logic App"
  value       = azapi_resource.workflow.id
}

output "workflow_name" {
  description = "Name of the deployed workflow"
  value       = azapi_resource.workflow.name
}

# ── Application Insights (azurerm) ───────────────────────────────────────────

output "application_insights_id" {
  description = "Resource ID of the Application Insights instance (one-to-one with this Logic App)"
  value       = azurerm_application_insights.this.id
}

output "application_insights_instrumentation_key" {
  description = "Instrumentation key for Application Insights (sensitive)"
  value       = azurerm_application_insights.this.instrumentation_key
  sensitive   = true
}

output "application_insights_connection_string" {
  description = "Connection string for Application Insights (sensitive)"
  value       = azurerm_application_insights.this.connection_string
  sensitive   = true
}

output "application_insights_app_id" {
  description = "Application ID of the Application Insights instance (for Kusto/Log Analytics queries)"
  value       = azurerm_application_insights.this.app_id
}
