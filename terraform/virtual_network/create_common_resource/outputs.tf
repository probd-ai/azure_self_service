output "nsg_ids" {
  value       = { for k, v in azurerm_network_security_group.nsgs : k => v.id }
  description = "Map of subnet name to NSG ID"
}
