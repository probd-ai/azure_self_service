# Virtual Network — create_common_resource

## What it does
Creates Network Security Groups (NSGs) and associates them with every subnet in the VNet. This is a **company policy requirement** — no subnet may exist without an NSG.

## When to use
Deploy this **immediately after** `virtual_network/create`. It must be deployed before any resources join the subnets (AKS, private endpoints, etc.).

## Important notes
- One NSG is created per subnet
- Default deny-all rules are applied; add specific allow rules via `nsg_rules` variable
- Naming convention: `nsg-<subnet-name>`

## Dependencies
- **Resource Group** (`resource_group/create`) — referenced via `data "azurerm_resource_group"`
- **Virtual Network** (`virtual_network/create`) — referenced via `data "azurerm_virtual_network"` and `data "azurerm_subnet"`

## Outputs
- `nsg_ids` — map of subnet name → NSG ID
