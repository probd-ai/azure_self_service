variable "vnet_name" {
  type        = string
  description = "Name of the VNet. Convention: vnet-<project>-<environment>-<region>"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group to deploy into"
}

variable "address_space" {
  type        = list(string)
  description = "CIDR address space for the VNet, e.g. [\"10.0.0.0/16\"]"
}

variable "subnets" {
  type = list(object({
    name             = string
    address_prefix   = string
    service_endpoints = optional(list(string), [])
  }))
  description = "List of subnets to create within this VNet"
}

variable "dns_servers" {
  type        = list(string)
  default     = []
  description = "Custom DNS server IPs. Leave empty to use Azure-provided DNS."
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
