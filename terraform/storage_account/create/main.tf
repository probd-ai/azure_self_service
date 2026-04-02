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

# Optional dependency: Subnet for private endpoint (only if enable_private_endpoint = true)
data "azurerm_subnet" "pe_subnet" {
  count                = var.enable_private_endpoint ? 1 : 0
  name                 = var.private_endpoint_subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = var.resource_group_name
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

resource "azurerm_storage_account" "this" {
  name                     = var.name
  resource_group_name      = data.azurerm_resource_group.this.name
  location                 = data.azurerm_resource_group.this.location
  account_tier             = var.account_tier
  account_replication_type = var.replication_type
  is_hns_enabled           = var.is_hns_enabled

  # Policy: HTTPS only, min TLS 1.2, no public blob access
  enable_https_traffic_only       = true
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false

  tags = merge(local.mandatory_tags, var.tags)
}

resource "azurerm_storage_container" "containers" {
  for_each              = { for c in var.containers : c.name => c }
  name                  = each.value.name
  storage_account_name  = azurerm_storage_account.this.name
  container_access_type = "private"
}

resource "azurerm_private_endpoint" "blob_pe" {
  count               = var.enable_private_endpoint ? 1 : 0
  name                = "pe-${var.name}-blob"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  subnet_id           = data.azurerm_subnet.pe_subnet[0].id

  private_service_connection {
    name                           = "psc-${var.name}-blob"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  tags = merge(local.mandatory_tags, var.tags)
}
