# Logic App — Common Resource

Deploys the **shared infrastructure** that multiple Logic App Standard instances
reuse within the same environment. Deploy this template **once per environment**;
all Logic Apps in that environment share these resources.

---

## What This Template Creates

| Resource | Provider Used | Azure Type | Purpose |
|---|---|---|---|
| App Service Plan | **azurerm** | `azurerm_service_plan` | Shared compute; all Logic Apps in the env run on this plan |
| Storage Account | **azurerm** | `azurerm_storage_account` | Shared workflow state, definitions, and runtime checkpoints |
| Log Analytics Workspace | **azurerm** | `azurerm_log_analytics_workspace` | Centralised log sink for all Logic Apps in this env |
| User-Assigned Managed Identity | **azurerm** | `azurerm_user_assigned_identity` | Shared identity for storage access and Key Vault references |
| Service Bus API Connection | **azapi** | `Microsoft.Web/connections` | Shared Service Bus connector reused by all Logic Apps |
| Service Bus Managed API (data) | **azapi** | `Microsoft.Web/locations/managedApis` | Connector schema/metadata lookup (data source only) |

---

## Why Mixed Providers?

This template uses **both `azurerm` and `azapi`**:

- **`azurerm`** handles resources that are fully supported by the AzureRM Terraform provider
  (App Service Plan, Storage Account, Log Analytics, Managed Identity).

- **`azapi`** is required for `Microsoft.Web/connections` because:
  - The `azurerm` provider has **no resource type** for managed API connections
  - The `parameterValues.connectionString` property can only be set via raw ARM JSON,
    which `azapi_resource` sends directly to the Azure Resource Manager API

---

## Config Module

Both provider blocks import the shared `terraform/config` module:

```hcl
module "config" {
  source = "../../config"
}
```

This provides:
- **`config/output.tf`** — `subscription_id`, `tenant_id`, `required_tags`
- **`config/azapi_api_output.tf`** — pinned API version strings for all `azapi` resource types

API versions are referenced as `module.config.azapi_api_connection_api_version` instead of
hardcoded strings, so upgrading an API version only requires a change in one place.

---

## Dependencies

| Must Exist First | Template | Why |
|---|---|---|
| Resource Group | `terraform/resource_group/create/` | All resources deploy into an existing RG |

---

## Deployment Order

```
1. terraform/resource_group/create/          ← must exist first
2. terraform/logic_app/create_common_resource/   ← this template (once per env)
3. terraform/logic_app/create/               ← one run per Logic App instance
```

---

## Important Notes

- **Storage account name** is auto-derived: `st<prefix>logic` with hyphens removed,
  truncated to 24 characters. Ensure the result is globally unique.
- **Service Bus connection string** is `sensitive = true` — store it in a separate
  `terraform.tfvars.sensitive` file and **never commit it** to version control.
- `lifecycle { ignore_changes = [body] }` on the API connection means Terraform will
  **not re-apply** the connection string on subsequent runs. Rotate it directly in the
  Azure portal or via the Azure CLI.
- The **shared Managed Identity** must be granted `Storage Blob Data Owner` on the storage
  account — this role assignment is created per Logic App in `logic_app/create/`.

---

## Outputs Consumed by `logic_app/create/`

| Output | Variable in `create/` |
|---|---|
| `app_service_plan_name` | `app_service_plan_name` |
| `storage_account_name` | `storage_account_name` |
| `managed_identity_name` | `managed_identity_name` |
| `log_analytics_workspace_name` | `log_analytics_workspace_name` |
| `servicebus_connection_id` | `servicebus_connection_id` |

---

## Naming Conventions

| Resource | Pattern |
|---|---|
| App Service Plan | `asp-<prefix>-logic` |
| Storage Account | `st<prefix>logic` (hyphens stripped, max 24 chars) |
| Log Analytics Workspace | `law-<prefix>-logic` |
| Managed Identity | `id-<prefix>-logic` |
| API Connection | `conn-<prefix>-servicebus` |
