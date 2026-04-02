terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

# Dependencies: Resource Group and VNet must already exist
data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

data "azurerm_virtual_network" "this" {
  name                = var.vnet_name
  resource_group_name = var.resource_group_name
}

data "azurerm_subnet" "subnets" {
  for_each             = toset(var.subnet_names)
  name                 = each.value
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

resource "azurerm_network_security_group" "nsgs" {
  for_each            = toset(var.subnet_names)
  name                = "nsg-${each.value}"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  tags                = merge(local.mandatory_tags, var.tags)
}

resource "azurerm_subnet_network_security_group_association" "assoc" {
  for_each                  = toset(var.subnet_names)
  subnet_id                 = data.azurerm_subnet.subnets[each.value].id
  network_security_group_id = azurerm_network_security_group.nsgs[each.value].id
}
