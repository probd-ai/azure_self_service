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

resource "azurerm_virtual_network" "this" {
  name                = var.vnet_name
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  address_space       = var.address_space
  dns_servers         = var.dns_servers
  tags                = merge(local.mandatory_tags, var.tags)
}

resource "azurerm_subnet" "subnets" {
  for_each             = { for s in var.subnets : s.name => s }
  name                 = each.value.name
  resource_group_name  = data.azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [each.value.address_prefix]
  service_endpoints    = lookup(each.value, "service_endpoints", [])
}
