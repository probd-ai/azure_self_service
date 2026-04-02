variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group"
}

variable "acr_name" {
  type        = string
  description = "Azure Container Registry name. Must be globally unique, 5-50 alphanumeric chars, no hyphens."
}

variable "acr_sku" {
  type        = string
  default     = "Standard"
  description = "ACR SKU: Basic, Standard, or Premium"
}

variable "law_name" {
  type        = string
  description = "Log Analytics Workspace name. Convention: law-<project>-<environment>"
}

variable "law_retention_days" {
  type        = number
  default     = 30
  description = "Log retention in days (minimum 30 for compliance)"
}

variable "managed_identity_name" {
  type        = string
  description = "Name of the user-assigned managed identity for AKS"
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
