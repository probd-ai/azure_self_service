# Logic App — Create

Deploys a **single Logic App Standard instance** and its one-to-one dependent
resources. Run this template once per Logic App; it consumes shared infrastructure
from `logic_app/create_common_resource/`.

---

## What This Template Creates

| Resource | Provider Used | Azure Type | Relationship to Logic App |
|---|---|---|---|
| Logic App Standard | **azapi** | `Microsoft.Web/sites` | The Logic App itself |
| Workflow Definition | **azapi** | `Microsoft.Web/sites/workflows` | One per Logic App — the actual workflow code |
| Diagnostic Settings | **azapi** | `Microsoft.Insights/diagnosticSettings` | One per Logic App — log/metric routing |
| Application Insights | **azurerm** | `azurerm_application_insights` | One per Logic App — per-app tracing |
| Role Assignment | **azurerm** | `azurerm_role_assignment` | One per Logic App — storage identity access |

---

## Why Mixed Providers?

This template uses **both `azurerm` and `azapi`**:

**`azurerm`** handles two resources that are fully supported:
- `azurerm_application_insights` — stable, complete property coverage
- `azurerm_role_assignment` — standard RBAC; no missing properties

**`azapi`** is required for three resources:

| Resource | Why azapi Is Needed |
|---|---|
| `Microsoft.Web/sites` (Logic App Standard) | `azurerm_logic_app_standard` does **not** support identity-based storage (`AzureWebJobsStorage__credential = managedidentity`) or `keyVaultReferenceIdentity`. azapi sends full ARM JSON. |
| `Microsoft.Web/sites/workflows` | **No azurerm resource type exists** for workflow definitions inside Logic App Standard. azapi is the only option. |
| `Microsoft.Insights/diagnosticSettings` | `azurerm_monitor_diagnostic_setting` does **not** support the `WorkflowRuntime` log category for `Microsoft.Web/sites`. azapi PATCH avoids Logic App restart. |

---

## Config Module

Both providers import the shared `terraform/config` module:

```hcl
module "config" {
  source = "../../config"
}
```

This provides:
- **`config/output.tf`** — `subscription_id`, `tenant_id`, `required_tags`
- **`config/azapi_api_output.tf`** — pinned API versions:
  - `azapi_logic_app_standard_api_version` → used in `Microsoft.Web/sites@<version>`
  - `azapi_logic_app_workflow_api_version` → used in `Microsoft.Web/sites/workflows@<version>`
  - `azapi_diagnostic_settings_api_version` → used in `Microsoft.Insights/diagnosticSettings@<version>`

---

## Dependencies

| Must Exist First | Template | Why |
|---|---|---|
| Resource Group | `terraform/resource_group/create/` | All resources deploy into this RG |
| App Service Plan | `terraform/logic_app/create_common_resource/` | Logic App needs compute host |
| Storage Account | `terraform/logic_app/create_common_resource/` | Runtime state and workflow definitions |
| User-Assigned Managed Identity | `terraform/logic_app/create_common_resource/` | Identity-based storage access |
| Log Analytics Workspace | `terraform/logic_app/create_common_resource/` | Diagnostic log destination |
| Service Bus API Connection | `terraform/logic_app/create_common_resource/` | Shared connector reference in workflow |

---

## Deployment Order

```
1. terraform/resource_group/create/
2. terraform/logic_app/create_common_resource/     ← shared infra, once per environment
3. terraform/logic_app/create/                     ← this template, once per Logic App
```

---

## Workflow Definition

The `workflow_definition` variable accepts a JSON string of the workflow definition body.

Minimal stateful workflow triggered by HTTP:

```json
{
  "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
  "contentVersion": "1.0.0.0",
  "triggers": {
    "manual": {
      "type": "Request",
      "kind": "Http",
      "inputs": { "schema": {} }
    }
  },
  "actions": {},
  "outputs": {}
}
```

Pass it as a single-line JSON string in `terraform.tfvars`:
```hcl
workflow_definition = "{\"$schema\":\"...\",\"contentVersion\":\"1.0.0.0\",\"triggers\":{},\"actions\":{},\"outputs\":{}}"
```

Or use `file()` and `jsonencode()` in a wrapper module.

---

## Important Notes

- **Identity-based storage**: The Logic App uses the shared Managed Identity to access
  storage. No connection string is stored in the app settings. The Managed Identity
  must have `Storage Blob Data Owner` — this is handled by `azurerm_role_assignment.logic_storage`.
- **`always_on = true`** is recommended for production to avoid cold starts on the
  Consumption plan.
- **Workflow state** is persisted in Azure Storage, not in Terraform state. Destroying
  this template does not delete workflow run history stored in the storage account.
- The `SERVICEBUS_CONNECTION_ID` app setting lets the workflow JSON reference the
  shared connection as `@appsetting('SERVICEBUS_CONNECTION_ID')`.

---

## Naming Conventions

| Resource | Pattern |
|---|---|
| Logic App Standard | `logic-<workload>-<environment>` |
| Application Insights | `appi-<logic_app_name>` |
| Diagnostic Setting | `diag-<logic_app_name>` |
| Workflow | `main-workflow` (default, override with `workflow_name`) |
