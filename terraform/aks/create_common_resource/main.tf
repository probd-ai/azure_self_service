terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

# Dependency: Resource Group must already exist
data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

locals {
  mandatory_tags = {
    environment  = var.environment
    project      = var.project
    owner        = var.owner
    created_by   = "terraform"
    created_date = formatdate("YYYY-MM-DD", timestamp())
  }
}

resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  sku                 = var.acr_sku
  admin_enabled       = false # policy: admin access disabled, use RBAC
  tags                = merge(local.mandatory_tags, var.tags)
}

resource "azurerm_log_analytics_workspace" "law" {
  name                = var.law_name
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = var.law_retention_days
  tags                = merge(local.mandatory_tags, var.tags)
}

resource "azurerm_user_assigned_identity" "aks_identity" {
  name                = var.managed_identity_name
  resource_group_name = data.azurerm_resource_group.this.name
  location            = data.azurerm_resource_group.this.location
  tags                = merge(local.mandatory_tags, var.tags)
}

# Grant AKS identity AcrPull on the registry
resource "azurerm_role_assignment" "acr_pull" {
  principal_id         = azurerm_user_assigned_identity.aks_identity.principal_id
  role_definition_name = "AcrPull"
  scope                = azurerm_container_registry.acr.id
}
