# config/main.tf
#
# This is a shared configuration MODULE imported by every template in this
# project via:
#
#   module "config" {
#     source = "../../config"    # (adjust relative path as needed)
#   }
#
# It exposes two categories of outputs, defined in sibling files:
#   output.tf           → subscription/tenant IDs, required tags, common locals
#   azapi_api_output.tf → pinned API-version strings for every azapi resource type
#
# Child templates reference values as:
#   module.config.subscription_id
#   module.config.azapi_logic_app_standard_api_version
#   etc.

# ── Current caller identity ───────────────────────────────────────────────────
# Reads the subscription/tenant of the currently authenticated provider context.
# No provider block here — this module inherits the provider from the caller.

data "azurerm_client_config" "current" {}

locals {
  subscription_id = data.azurerm_client_config.current.subscription_id
  tenant_id       = data.azurerm_client_config.current.tenant_id
  client_id       = data.azurerm_client_config.current.client_id
}
