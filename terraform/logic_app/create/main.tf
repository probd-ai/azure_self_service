# ══════════════════════════════════════════════════════════════════════════════
# Data sources — azurerm
# Look up the shared resources created by logic_app/create_common_resource/.
# These MUST already exist; this template does not create them.
# ══════════════════════════════════════════════════════════════════════════════

data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

data "azurerm_service_plan" "shared" {
  name                = var.app_service_plan_name
  resource_group_name = var.resource_group_name
}

data "azurerm_storage_account" "shared" {
  name                = var.storage_account_name
  resource_group_name = var.resource_group_name
}

data "azurerm_user_assigned_identity" "shared" {
  name                = var.managed_identity_name
  resource_group_name = var.resource_group_name
}

data "azurerm_log_analytics_workspace" "shared" {
  name                = var.log_analytics_workspace_name
  resource_group_name = var.resource_group_name
}

# ── Locals ────────────────────────────────────────────────────────────────────

locals {
  common_tags = merge(module.config.required_tags, {
    environment   = var.environment
    project       = var.project
    owner         = var.owner
    logic-app     = var.logic_app_name
  }, var.tags)
}

# ══════════════════════════════════════════════════════════════════════════════
# azurerm resources — one-to-one with this Logic App instance
# Well-supported by the AzureRM provider; use standard resource blocks.
# ══════════════════════════════════════════════════════════════════════════════

# Application Insights — one instance per Logic App for granular per-app tracing.
# Workspace-based (linked to the shared Log Analytics Workspace).
resource "azurerm_application_insights" "this" {
  name                = "appi-${var.logic_app_name}"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  workspace_id        = data.azurerm_log_analytics_workspace.shared.id
  application_type    = "web"
  retention_in_days   = var.app_insights_retention_days
  tags                = local.common_tags
}

# Role assignment — grants the shared Managed Identity "Storage Blob Data Owner"
# on the shared storage account so this Logic App can read/write its workflow state
# using identity-based authentication (no connection string stored in config).
resource "azurerm_role_assignment" "logic_storage" {
  scope                = data.azurerm_storage_account.shared.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_user_assigned_identity.shared.principal_id
}

# ══════════════════════════════════════════════════════════════════════════════
# azapi resources
# Three resources here require azapi because the AzureRM provider either has no
# support or incomplete property coverage for these ARM resource types.
# API versions are sourced from module.config (config/azapi_api_output.tf).
# ══════════════════════════════════════════════════════════════════════════════

# Logic App Standard — deployed via azapi_resource because azurerm_logic_app_standard:
#   ✗ Does NOT support identity-based storage (AzureWebJobsStorage__credential)
#   ✗ Does NOT support keyVaultReferenceIdentity for Key Vault references
#   ✗ Does NOT expose all siteConfig properties (e.g. functionsRuntimeScaleMonitoringEnabled)
#
# API version: module.config.azapi_logic_app_standard_api_version
resource "azapi_resource" "logic_app" {
  type      = module.config.azapi_logic_app_standard_api_version
  name      = var.logic_app_name
  location  = data.azurerm_resource_group.this.location
  parent_id = data.azurerm_resource_group.this.id

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.shared.id]
  }

  body = jsonencode({
    kind = "functionapp,workflowapp"   # marks this Web/sites resource as a Logic App Standard
    properties = {
      serverFarmId = data.azurerm_service_plan.shared.id
      siteConfig = {
        alwaysOn = var.always_on
        appSettings = [
          # Runtime version — Logic App Standard uses Azure Functions v4 runtime
          { name = "FUNCTIONS_EXTENSION_VERSION",  value = "~4" },
          { name = "FUNCTIONS_WORKER_RUNTIME",     value = "node" },
          { name = "WEBSITE_NODE_DEFAULT_VERSION", value = "~18" },

          # Identity-based storage access — avoids storing a connection string in config
          # The Managed Identity must have Storage Blob Data Owner on this account
          { name = "AzureWebJobsStorage__accountName",  value = data.azurerm_storage_account.shared.name },
          { name = "AzureWebJobsStorage__credential",   value = "managedidentity" },
          { name = "AzureWebJobsStorage__clientId",     value = data.azurerm_user_assigned_identity.shared.client_id },

          # Application Insights
          { name = "APPINSIGHTS_INSTRUMENTATIONKEY",        value = azurerm_application_insights.this.instrumentation_key },
          { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = azurerm_application_insights.this.connection_string },

          # Service Bus connection ID — referenced in workflow JSON as @appsetting('SERVICEBUS_CONNECTION_ID')
          { name = "SERVICEBUS_CONNECTION_ID", value = var.servicebus_connection_id },
        ]
      }
      # Specifies which identity to use for @Microsoft.KeyVault() references in app settings
      keyVaultReferenceIdentity = data.azurerm_user_assigned_identity.shared.id
    }
  })

  tags = local.common_tags

  depends_on = [
    azurerm_role_assignment.logic_storage,   # identity must have storage access before app starts
    azurerm_application_insights.this,
  ]
}

# Workflow definition — deployed inside the Logic App Standard instance.
# azapi_resource is REQUIRED here because:
#   ✗ azurerm has NO resource type for Microsoft.Web/sites/workflows at all
#   The workflow definition JSON (triggers, actions, connections) is sent as raw ARM body.
#
# API version: module.config.azapi_logic_app_workflow_api_version
resource "azapi_resource" "workflow" {
  type      = "Microsoft.Web/sites/workflows@${module.config.azapi_logic_app_workflow_api_version}"
  name      = var.workflow_name
  parent_id = azapi_resource.logic_app.id

  body = jsonencode({
    properties = {
      kind = "Stateful"   # Stateful = checkpointed, supports long-running operations
      definition = jsondecode(var.workflow_definition)
      connections = {
        managedApiConnections = {
          servicebus = {
            api = {
              id = "/subscriptions/${module.config.subscription_id}/providers/Microsoft.Web/locations/${data.azurerm_resource_group.this.location}/managedApis/servicebus"
            }
            connection = {
              id = var.servicebus_connection_id
            }
            connectionRuntimeUrl = ""
            authentication = {
              type = "ManagedServiceIdentity"
            }
          }
        }
      }
    }
  })

  depends_on = [azapi_resource.logic_app]
}

# Diagnostic settings — streams Logic App logs and metrics to the shared workspace.
# azapi_update_resource is used because:
#   ✗ azurerm_monitor_diagnostic_setting does NOT support the WorkflowRuntime log
#     category for Microsoft.Web/sites resources
#   azapi_update_resource PATCHES the resource without replacing it, which avoids
#   triggering a restart of the Logic App.
#
# API version: module.config.azapi_diagnostic_settings_api_version
resource "azapi_update_resource" "logic_app_diagnostics" {
  type      = "Microsoft.Insights/diagnosticSettings@${module.config.azapi_diagnostic_settings_api_version}"
  name      = "diag-${var.logic_app_name}"
  parent_id = azapi_resource.logic_app.id

  body = jsonencode({
    properties = {
      workspaceId = data.azurerm_log_analytics_workspace.shared.id
      logs = [
        { category = "WorkflowRuntime", enabled = true, retentionPolicy = { enabled = false, days = 0 } },
        { category = "FunctionAppLogs", enabled = true, retentionPolicy = { enabled = false, days = 0 } },
      ]
      metrics = [
        { category = "AllMetrics", enabled = true, retentionPolicy = { enabled = false, days = 0 } }
      ]
    }
  })

  depends_on = [azapi_resource.logic_app]
}
