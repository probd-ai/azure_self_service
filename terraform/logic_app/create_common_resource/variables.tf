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
  description = "Name of the existing Resource Group to deploy shared Logic App resources into"
}

variable "location" {
  type        = string
  description = "Azure region for all resources, e.g. eastus, westeurope"
}

# ── Naming ────────────────────────────────────────────────────────────────────

variable "prefix" {
  type        = string
  description = "Short prefix for naming all shared resources. Convention: <project>-<env>. E.g. myapp-dev"
}

# ── App Service Plan ──────────────────────────────────────────────────────────

variable "app_service_plan_sku" {
  type        = string
  default     = "WS1"
  description = "App Service Plan SKU for Logic App Standard. Approved: WS1 (dev/test), WS2 (prod), WS3 (high-throughput)"
}

# ── Storage Account ───────────────────────────────────────────────────────────

variable "storage_replication_type" {
  type        = string
  default     = "LRS"
  description = "Storage Account replication: LRS (dev), GRS (prod), ZRS (zone-redundant)"
}

# ── Log Analytics Workspace ───────────────────────────────────────────────────

variable "law_retention_days" {
  type        = number
  default     = 30
  description = "Log retention in days (30–730). 90 days recommended for production."
}

# ── Service Bus API Connection ────────────────────────────────────────────────

variable "service_bus_connection_string" {
  type        = string
  description = "Service Bus namespace connection string for the shared managed-API connection. Store in terraform.tfvars.sensitive"
  sensitive   = true
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
  description = "Team or individual responsible for these shared resources"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags merged on top of required_tags from the config module"
}
