# Storage Account

## What it does
Creates an Azure Storage Account for storing blobs, files, queues, and tables. Supports optional private endpoint for secure, VNet-integrated access.

## When to use
- Storing application data, logs, or backups (Blob)
- Shared file storage (Azure Files)
- ADLS Gen2 for big data workloads (enable `is_hns_enabled`)
- Any service that needs durable cloud storage

## Important notes (company policy)
- `https_only = true` is enforced — no HTTP access
- `min_tls_version = TLS1_2` is enforced
- `public blob access is disabled` — no anonymous access allowed
- For production: deploy with `enable_private_endpoint = true` and connect to your VNet

## Dependencies
- **Resource Group** (`resource_group/create`) — referenced via `data "azurerm_resource_group"`
- **Virtual Network** (`virtual_network/create`) — only required if `enable_private_endpoint = true`, referenced via `data "azurerm_subnet"`

## Outputs
- `storage_account_id` — resource ID
- `storage_account_name` — storage account name
- `primary_blob_endpoint` — blob service URL
