variable "name" {
  type        = string
  description = "Storage account name: 3-24 lowercase alphanumeric chars, globally unique"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group"
}

variable "account_tier" {
  type        = string
  description = "Storage tier: Standard or Premium"
}

variable "replication_type" {
  type        = string
  description = "Replication: LRS, GRS, RAGRS, ZRS, GZRS"
}

variable "is_hns_enabled" {
  type        = bool
  default     = false
  description = "Enable hierarchical namespace for ADLS Gen2"
}

variable "enable_private_endpoint" {
  type        = bool
  default     = false
  description = "Deploy a private endpoint for blob access (recommended for prod)"
}

variable "private_endpoint_subnet_name" {
  type        = string
  default     = ""
  description = "Subnet name for private endpoint (required if enable_private_endpoint = true)"
}

variable "vnet_name" {
  type        = string
  default     = ""
  description = "VNet name for private endpoint (required if enable_private_endpoint = true)"
}

variable "containers" {
  type = list(object({
    name = string
  }))
  default     = []
  description = "Blob containers to create (all private access)"
}

variable "environment" {
  type        = string
  description = "Environment: dev, test, staging, or prod"
}

variable "project" {
  type        = string
  description = "Project or workload name"
}

variable "owner" {
  type        = string
  description = "Team or individual responsible"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags"
}
