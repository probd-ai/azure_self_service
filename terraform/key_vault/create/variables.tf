variable "name" {
  type        = string
  description = "Key Vault name: 3-24 chars, globally unique. Convention: kv-<project>-<environment>"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group"
}

variable "sku_name" {
  type        = string
  default     = "standard"
  description = "Key Vault SKU: standard or premium (premium required for HSM-backed keys)"
}

variable "enable_private_endpoint" {
  type        = bool
  default     = false
  description = "Deploy a private endpoint (recommended for prod)"
}

variable "private_endpoint_subnet_name" {
  type        = string
  default     = ""
  description = "Subnet name for private endpoint (required if enable_private_endpoint = true)"
}

variable "vnet_name" {
  type        = string
  default     = ""
  description = "VNet name (required if enable_private_endpoint = true)"
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
