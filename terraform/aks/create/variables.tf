variable "cluster_name" {
  type        = string
  description = "AKS cluster name. Convention: aks-<project>-<environment>-<region>"
}

variable "resource_group_name" {
  type        = string
  description = "Name of the existing Resource Group"
}

variable "dns_prefix" {
  type        = string
  description = "DNS prefix for the AKS cluster"
}

variable "kubernetes_version" {
  type        = string
  description = "Kubernetes version, e.g. 1.29.0"
}

variable "vnet_name" {
  type        = string
  description = "Name of the existing Virtual Network"
}

variable "aks_subnet_name" {
  type        = string
  description = "Name of the subnet within the VNet for AKS nodes"
}

variable "law_name" {
  type        = string
  description = "Name of the existing Log Analytics Workspace (from aks/create_common_resource)"
}

variable "managed_identity_name" {
  type        = string
  description = "Name of the existing User-Assigned Managed Identity (from aks/create_common_resource)"
}

variable "key_vault_name" {
  type        = string
  description = "Name of the existing Key Vault (from key_vault/create)"
}

variable "system_node_pool_vm_size" {
  type        = string
  description = "VM size for system node pool. Approved sizes: Standard_D4s_v3, Standard_D8s_v3, etc."
}

variable "system_node_pool_count" {
  type        = number
  default     = 1
  description = "Node count when autoscaling is disabled"
}

variable "enable_auto_scaling" {
  type        = bool
  default     = true
  description = "Enable cluster autoscaler"
}

variable "min_node_count" {
  type        = number
  default     = 1
  description = "Minimum nodes when autoscaling is enabled"
}

variable "max_node_count" {
  type        = number
  default     = 5
  description = "Maximum nodes when autoscaling is enabled"
}

variable "private_cluster_enabled" {
  type        = bool
  default     = false
  description = "Make the AKS API server private. Required for prod environments."
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
