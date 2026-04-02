output "storage_account_id" {
  value       = azurerm_storage_account.this.id
  description = "Azure resource ID of the Storage Account"
}

output "storage_account_name" {
  value       = azurerm_storage_account.this.name
  description = "Storage Account name"
}

output "primary_blob_endpoint" {
  value       = azurerm_storage_account.this.primary_blob_endpoint
  description = "Primary blob service endpoint URL"
}
