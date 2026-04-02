output "vnet_id" {
  value       = azurerm_virtual_network.this.id
  description = "Azure resource ID of the Virtual Network"
}

output "vnet_name" {
  value       = azurerm_virtual_network.this.name
  description = "Name of the Virtual Network"
}

output "subnet_ids" {
  value       = { for k, v in azurerm_subnet.subnets : k => v.id }
  description = "Map of subnet name to subnet ID"
}
