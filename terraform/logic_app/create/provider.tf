terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 1.12"
    }
  }
  required_version = ">= 1.6.0"
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  client_id       = var.client_id
  client_secret   = var.client_secret
}

provider "azapi" {
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
  client_id       = var.client_id
  client_secret   = var.client_secret
}

# ── Shared config module ──────────────────────────────────────────────────────
# Imports two files from terraform/config/:
#   output.tf           → subscription_id, tenant_id, required_tags
#   azapi_api_output.tf → pinned API version strings for all azapi resource types
#
# Usage:
#   module.config.subscription_id
#   module.config.azapi_logic_app_standard_api_version
#   module.config.azapi_logic_app_workflow_api_version
#   module.config.azapi_diagnostic_settings_api_version

module "config" {
  source = "../../config"
}
