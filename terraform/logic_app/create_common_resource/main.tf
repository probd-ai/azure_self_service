# ── Data sources — azurerm ────────────────────────────────────────────────────
# Reads the pre-existing Resource Group created by terraform/resource_group/create/

data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

# ── Locals ────────────────────────────────────────────────────────────────────

locals {
  # Merge project tags with the mandatory tags from the config module
  common_tags = merge(module.config.required_tags, {
    environment = var.environment
    project     = var.project
    owner       = var.owner
  }, var.tags)

  # Full subscription scope — required by azapi resources and data sources
  # that use ARM resource IDs instead of Terraform references
  subscription_scope = "/subscriptions/${module.config.subscription_id}"
}

# ══════════════════════════════════════════════════════════════════════════════
# azurerm resources
# These are well-supported by the AzureRM provider and use standard Terraform
# resource types. Deployed once and shared across all Logic App instances in
# this environment.
# ══════════════════════════════════════════════════════════════════════════════

# Shared App Service Plan — all Logic App Standard instances in this environment
# run on this plan. Scaling the plan affects all logic apps simultaneously.
resource "azurerm_service_plan" "logic_shared" {
  name                = "asp-${var.prefix}-logic"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.location
  os_type             = "Windows"      # Logic App Standard requires Windows hosting
  sku_name            = var.app_service_plan_sku
  tags                = local.common_tags
}

# Shared Storage Account — Logic App Standard uses this for:
#   - Workflow state (stateful workflows)
#   - Workflow definitions (JSON stored as blobs)
#   - Checkpoint and lease data for the runtime
resource "azurerm_storage_account" "logic_state" {
  name                     = substr(replace("st${var.prefix}logic", "-", ""), 0, 24)
  resource_group_name      = data.azurerm_resource_group.this.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = var.storage_replication_type
  min_tls_version          = "TLS1_2"
  tags                     = local.common_tags
}

# Shared Log Analytics Workspace — receives diagnostic logs and metrics from all
# Logic App instances in this environment via azapi_update_resource diagnostics
resource "azurerm_log_analytics_workspace" "logic_law" {
  name                = "law-${var.prefix}-logic"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.law_retention_days
  tags                = local.common_tags
}

# Shared User-Assigned Managed Identity — used by all Logic App instances to:
#   - Access shared storage without a connection string (identity-based auth)
#   - Reference Key Vault secrets
#   - Authenticate to API connections
resource "azurerm_user_assigned_identity" "logic_identity" {
  name                = "id-${var.prefix}-logic"
  resource_group_name = data.azurerm_resource_group.this.name
  location            = var.location
  tags                = local.common_tags
}

# ══════════════════════════════════════════════════════════════════════════════
# azapi resources
# The AzureRM provider does NOT support Microsoft.Web/connections with full
# parameterValues properties. azapi sends the raw ARM JSON directly, giving
# full control over all connection properties.
# ══════════════════════════════════════════════════════════════════════════════

# Shared Service Bus API Connection — a managed-API connector that all Logic Apps
# in this environment can reference. Created via azapi because:
#   - azurerm has no resource type for Microsoft.Web/connections
#   - The parameterValues.connectionString property is not exposed in any azurerm resource
#
# API version sourced from module.config.azapi_api_connection_api_version (config/azapi_api_output.tf)
resource "azapi_resource" "servicebus_connection" {
  type      = "Microsoft.Web/connections@${module.config.azapi_api_connection_api_version}"
  name      = "conn-${var.prefix}-servicebus"
  location  = var.location
  parent_id = data.azurerm_resource_group.this.id

  body = jsonencode({
    properties = {
      displayName = "Shared Service Bus Connection — ${var.prefix}"
      api = {
        # ARM resource ID of the built-in Service Bus managed API
        id = "${local.subscription_scope}/providers/Microsoft.Web/locations/${var.location}/managedApis/servicebus"
      }
      parameterValues = {
        connectionString = var.service_bus_connection_string
      }
    }
  })

  tags = local.common_tags

  lifecycle {
    # Ignore body changes after creation — connection string rotation is handled
    # outside Terraform (e.g. Key Vault reference or manual update) to avoid
    # re-applying the sensitive value on every plan run.
    ignore_changes = [body]
  }
}

# Data source for Service Bus managed API metadata — used to discover the connector
# schema, trigger definitions, and action definitions.
# azurerm has NO equivalent for Microsoft.Web/locations/managedApis.
# API version sourced from module.config.azapi_managed_api_api_version
data "azapi_resource" "servicebus_managed_api" {
  type      = "Microsoft.Web/locations/managedApis@${module.config.azapi_managed_api_api_version}"
  name      = "servicebus"
  parent_id = "${local.subscription_scope}/providers/Microsoft.Web/locations/${var.location}"

  response_export_values = ["properties.generalInformation", "properties.capabilities"]
}
