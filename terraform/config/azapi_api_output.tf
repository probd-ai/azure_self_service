# config/azapi_api_output.tf
#
# Pinned API-version strings for EVERY resource type deployed via azapi_resource
# or azapi_update_resource in this project.
#
# WHY THIS EXISTS
# ───────────────
# azapi resources require an explicit API version in their `type` field:
#   type = "Microsoft.Web/sites@2023-12-01"
#
# Hardcoding the version string in each template creates drift risk. Instead,
# every template reads the version from here:
#   type = "Microsoft.Web/sites@${module.config.azapi_logic_app_standard_api_version}"
#
# To upgrade an API version for the whole project, change it once here.
#
# HOW TO FIND THE CORRECT API VERSION
# ────────────────────────────────────
# az provider show --namespace Microsoft.Web --query "resourceTypes[?resourceType=='sites'].apiVersions"

# ── Logic App Standard (Microsoft.Web/sites with kind=functionapp,workflowapp) ─
output "azapi_logic_app_standard_api_version" {
  description = "API version for Logic App Standard: Microsoft.Web/sites"
  value       = "2023-12-01"
}

# ── Workflow definitions inside a Logic App Standard instance ─────────────────
output "azapi_logic_app_workflow_api_version" {
  description = "API version for Logic App workflows: Microsoft.Web/sites/workflows"
  value       = "2023-12-01"
}

# ── API Connections (classic managed-API connectors, e.g. Service Bus, O365) ──
output "azapi_api_connection_api_version" {
  description = "API version for managed API connections: Microsoft.Web/connections"
  value       = "2016-06-01"
}

# ── Managed API metadata (connector discovery, used in data sources) ──────────
output "azapi_managed_api_api_version" {
  description = "API version for connector metadata: Microsoft.Web/locations/managedApis"
  value       = "2016-06-01"
}

# ── Diagnostic Settings (all resource types) ──────────────────────────────────
output "azapi_diagnostic_settings_api_version" {
  description = "API version for diagnostic settings: Microsoft.Insights/diagnosticSettings"
  value       = "2021-05-01-preview"
}
