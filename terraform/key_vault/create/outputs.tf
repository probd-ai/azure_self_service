output "key_vault_id" {
  value       = azurerm_key_vault.this.id
  description = "Azure resource ID of the Key Vault"
}

output "key_vault_name" {
  value       = azurerm_key_vault.this.name
  description = "Key Vault name"
}

output "key_vault_uri" {
  value       = azurerm_key_vault.this.vault_uri
  description = "Key Vault URI, e.g. https://myvault.vault.azure.net/"
}
