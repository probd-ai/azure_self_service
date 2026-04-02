variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group"
}

variable "vnet_name" {
  type        = string
  description = "Name of the existing Virtual Network"
}

variable "subnet_names" {
  type        = list(string)
  description = "List of subnet names that need NSG associations"
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
