# Virtual Network — create

## What it does
Creates an Azure Virtual Network (VNet) with one or more subnets. The VNet provides network isolation and private connectivity for all Azure resources that join it.

## When to use
Deploy a VNet when any of the following are required:
- AKS cluster (requires a subnet for nodes)
- Private endpoints for Storage Account or Key Vault
- Any workload that must not be exposed to the public internet

## Important notes
- Every subnet created here is automatically associated with a Network Security Group (NSG) — created in `create_common_resource/`
- Address space must not overlap with other VNets in the environment
- Naming convention: `vnet-<project>-<environment>-<region>`

## Dependencies
- **Resource Group** (`resource_group/create`) — must exist first. Referenced via `data "azurerm_resource_group"`.

## Outputs
- `vnet_id` — Azure resource ID of the VNet
- `vnet_name` — name of the VNet
- `subnet_ids` — map of subnet name → subnet ID (used by AKS, private endpoints, etc.)
