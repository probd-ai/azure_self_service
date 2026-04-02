# config/output.tf
#
# General shared outputs: identity context + mandatory tagging policy.
# Imported by all templates via `module "config"`.

output "subscription_id" {
  description = "Azure Subscription ID of the currently authenticated context"
  value       = local.subscription_id
}

output "tenant_id" {
  description = "Azure AD Tenant ID of the currently authenticated context"
  value       = local.tenant_id
}

output "client_id" {
  description = "Client ID of the Service Principal or Managed Identity in use"
  value       = local.client_id
}

# ── Mandatory resource tags ───────────────────────────────────────────────────
# Every resource deployed by any template MUST carry these tags (policy enforced).
# Templates merge their own tags on top of these.

output "required_tags" {
  description = "Mandatory tags that must be applied to every Azure resource in this project"
  value = {
    "managed-by"   = "terraform"
    "project"      = "azure-self-service"
    "source-repo"  = "azure-self-service-agent"
  }
}
