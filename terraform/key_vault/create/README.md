# Key Vault

## What it does
Creates an Azure Key Vault for storing secrets, encryption keys, and certificates. Required by AKS (secrets provider addon) and any service that needs secure credential storage.

## When to use
- Storing application secrets, API keys, connection strings
- Encryption key management
- Certificate lifecycle management
- Any workload that needs to pull secrets at runtime (especially AKS with CSI driver)

## Important notes (company policy)
- `soft_delete_retention_days = 90` — enforced, cannot be lower
- `purge_protection_enabled = true` — enforced, prevents accidental permanent deletion
- `enable_rbac_authorization = true` — RBAC-based access (not legacy access policies)
- For production: use `enable_private_endpoint = true`

## Dependencies
- **Resource Group** (`resource_group/create`) — referenced via `data "azurerm_resource_group"`
- **Virtual Network** (`virtual_network/create`) — only required if `enable_private_endpoint = true`, referenced via `data "azurerm_subnet"`

## Outputs
- `key_vault_id` — resource ID
- `key_vault_name` — vault name
- `key_vault_uri` — vault URI (e.g. https://myvault.vault.azure.net/)
