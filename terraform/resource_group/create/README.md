# Resource Group

## What it does
Creates an Azure Resource Group — the logical container that holds all related Azure resources for a workload. Every single Azure resource must belong to a resource group.

## When to use
This is always **Step 1** of any deployment. No other Azure resource can be created without a resource group existing first.

## Important notes
- The name must follow company naming convention: `rg-<project>-<environment>-<region>`
- Mandatory tags are enforced: `environment`, `project`, `owner`, `created_by`, `created_date`
- Allowed environments: `dev`, `test`, `staging`, `prod`
- Allowed regions: `eastus`, `eastus2`, `westus2`, `westeurope`, `northeurope`

## Dependencies
None — this is the base dependency for everything else.

## Outputs
- `resource_group_id` — the full Azure resource ID
- `resource_group_name` — the name (referenced by all downstream resources)
- `resource_group_location` — the region
