variable "name" {
  type        = string
  description = "Name of the resource group. Convention: rg-<project>-<environment>-<region>"
}

variable "location" {
  type        = string
  description = "Azure region. Allowed: eastus, eastus2, westus2, westeurope, northeurope"
}

variable "environment" {
  type        = string
  description = "Deployment environment: dev, test, staging, or prod"
}

variable "project" {
  type        = string
  description = "Project or workload name"
}

variable "owner" {
  type        = string
  description = "Team or individual responsible for this resource group"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional custom tags to merge with mandatory tags"
}
