# ── Authentication (sensitive — store in terraform.tfvars.sensitive) ──────────

variable "subscription_id" {
  type        = string
  description = "Azure Subscription ID"
  sensitive   = true
}

variable "tenant_id" {
  type        = string
  description = "Azure AD Tenant ID"
  sensitive   = true
}

variable "client_id" {
  type        = string
  description = "Service Principal client ID"
  sensitive   = true
}

variable "client_secret" {
  type        = string
  description = "Service Principal client secret"
  sensitive   = true
}

# ── Placement ─────────────────────────────────────────────────────────────────

variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group (same RG as create_common_resource)"
}

variable "location" {
  type        = string
  description = "Azure region, e.g. eastus, westeurope — must match create_common_resource location"
}

# ── This Logic App instance ───────────────────────────────────────────────────

variable "logic_app_name" {
  type        = string
  description = "Name of this Logic App Standard instance. Convention: logic-<workload>-<environment>"
}

variable "always_on" {
  type        = bool
  default     = false
  description = "Keep the Logic App always warm. Set true for production to eliminate cold starts."
}

variable "app_insights_retention_days" {
  type        = number
  default     = 30
  description = "Application Insights data retention in days (30–730). 90 recommended for prod."
}

# ── Workflow definition ───────────────────────────────────────────────────────

variable "workflow_name" {
  type        = string
  default     = "main-workflow"
  description = "Name of the workflow inside the Logic App Standard instance"
}

variable "workflow_definition" {
  type        = string
  default     = "{}"
  description = "JSON string of the Logic App workflow definition body. See README for a minimal example."
}

# ── References to create_common_resource outputs ──────────────────────────────

variable "app_service_plan_name" {
  type        = string
  description = "Name of the shared App Service Plan (output app_service_plan_name from create_common_resource)"
}

variable "storage_account_name" {
  type        = string
  description = "Name of the shared storage account (output storage_account_name from create_common_resource)"
}

variable "managed_identity_name" {
  type        = string
  description = "Name of the shared User-Assigned Managed Identity (output managed_identity_name from create_common_resource)"
}

variable "log_analytics_workspace_name" {
  type        = string
  description = "Name of the shared Log Analytics Workspace (output log_analytics_workspace_name from create_common_resource)"
}

variable "servicebus_connection_id" {
  type        = string
  description = "Resource ID of the shared Service Bus API connection (output servicebus_connection_id from create_common_resource)"
}

# ── Tagging ───────────────────────────────────────────────────────────────────

variable "environment" {
  type        = string
  description = "Deployment environment: dev, test, staging, prod"
}

variable "project" {
  type        = string
  description = "Project or workload name"
}

variable "owner" {
  type        = string
  description = "Team or individual responsible for this Logic App"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags merged on top of required_tags from the config module"
}
