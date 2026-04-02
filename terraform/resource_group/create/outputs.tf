output "resource_group_id" {
  value       = azurerm_resource_group.this.id
  description = "The Azure resource ID of the resource group"
}

output "resource_group_name" {
  value       = azurerm_resource_group.this.name
  description = "The name of the resource group"
}

output "resource_group_location" {
  value       = azurerm_resource_group.this.location
  description = "The Azure region of the resource group"
}
