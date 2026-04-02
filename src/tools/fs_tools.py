"""
fs_tools.py — Agent tools
Five tools for exploring and understanding Terraform templates.
"""
import os
import re
from pathlib import Path
from src.config.settings import settings


# Maps Terraform data-source resource types to the template folder(s) that create them.
# A resource type can appear in multiple templates (e.g. azurerm_storage_account is
# created by both storage_account/create/ and logic_app/create_common_resource/).
# When multiple sources exist the agent must use context to pick the right one.
_RESOURCE_TO_TEMPLATES: dict[str, list[str]] = {
    "azurerm_resource_group":           ["terraform/resource_group/create/"],
    "azurerm_virtual_network":          ["terraform/virtual_network/create/"],
    "azurerm_subnet":                   ["terraform/virtual_network/create/"],
    "azurerm_key_vault":                ["terraform/key_vault/create/"],
    "azurerm_storage_account":          ["terraform/storage_account/create/",
                                         "terraform/logic_app/create_common_resource/"],
    "azurerm_kubernetes_cluster":       ["terraform/aks/create/"],
    "azurerm_log_analytics_workspace":  ["terraform/aks/create_common_resource/",
                                         "terraform/logic_app/create_common_resource/"],
    "azurerm_user_assigned_identity":   ["terraform/aks/create_common_resource/",
                                         "terraform/logic_app/create_common_resource/"],
    "azurerm_service_plan":             ["terraform/logic_app/create_common_resource/"],
    "azurerm_application_insights":     ["terraform/logic_app/create/"],
}

# azapi data sources use the generic type "azapi_resource" — the actual Azure resource
# type is embedded inside the `type` attribute as a string, not extractable by regex alone.
# These are flagged separately so the agent can inspect them manually if needed.
_AZAPI_DATA_SOURCE_TYPES = {"azapi_resource", "azapi_resource_list"}

# Variable names that contain secrets — shown with a warning
_SENSITIVE_NAMES = {"client_secret", "password", "secret", "api_key", "access_key",
                    "subscription_id", "tenant_id", "client_id"}


def list_directory(path: str) -> dict:
    """
    List the contents of a directory inside the terraform base path.
    Returns folders and files separately so the LLM can navigate the structure.

    Args:
        path: Relative path from project root (e.g. "terraform/" or "terraform/aks/create")
    """
    target = Path(path)

    # Allow absolute paths that are within the project, or relative paths
    if not target.is_absolute():
        target = Path(".") / target

    if not target.exists():
        return {"error": f"Path does not exist: {path}"}

    if not target.is_dir():
        return {"error": f"Path is a file, not a directory: {path}. Use read_file instead."}

    dirs, files = [], []
    for entry in sorted(target.iterdir()):
        if entry.is_dir():
            dirs.append(entry.name)
        else:
            files.append(entry.name)

    return {
        "path": str(target),
        "directories": dirs,
        "files": files,
    }


def read_file(path: str) -> dict:
    """
    Read the full content of a file (Terraform .tf files, README.md, etc).

    Args:
        path: Relative path from project root (e.g. "terraform/aks/create/main.tf")
    """
    target = Path(path)

    if not target.is_absolute():
        target = Path(".") / target

    if not target.exists():
        return {"error": f"File does not exist: {path}"}

    if target.is_dir():
        return {"error": f"Path is a directory, not a file: {path}. Use list_directory instead."}

    try:
        content = target.read_text(encoding="utf-8")
        return {
            "path": str(target),
            "content": content,
        }
    except Exception as e:
        return {"error": f"Could not read file: {e}"}


# ── Tool 3: find_dependencies ─────────────────────────────────────────────────

def find_dependencies(path: str) -> dict:
    """
    Parse a main.tf file (or directory containing one) and extract every
    data{} block to produce a guaranteed-correct dependency list.
    Returns which templates must be deployed BEFORE this one.

    Args:
        path: Path to a main.tf file or the template directory containing it.
    """
    target = Path(path) if Path(path).is_absolute() else Path(".") / path
    if target.is_dir():
        target = target / "main.tf"

    if not target.exists():
        return {"error": f"main.tf not found at: {target}"}

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    # Extract all  data "resource_type" "alias" {  blocks
    data_blocks = re.findall(r'data\s+"([^"]+)"\s+"([^"]+)"', content)

    deps = []
    seen_templates: set[str] = set()
    unknown: list[str] = []
    azapi_data_sources: list[str] = []

    for resource_type, alias in data_blocks:
        # azapi data sources — the real ARM type is inside the `type` attribute string,
        # not in the data block header, so we flag them separately for the agent to inspect
        if resource_type in _AZAPI_DATA_SOURCE_TYPES:
            azapi_data_sources.append(alias)
            continue

        templates = _RESOURCE_TO_TEMPLATES.get(resource_type)
        if templates:
            for template in templates:
                if template not in seen_templates:
                    seen_templates.add(template)
                    deps.append({
                        "depends_on_template": template,
                        "reason": f'Reads an existing {resource_type} via data source "{alias}"',
                        "must_exist_before_deploy": True,
                        "ambiguous": len(templates) > 1,
                        "alternative_sources": [t for t in templates if t != template] if len(templates) > 1 else [],
                        "note": (
                            f"Multiple templates can create {resource_type}. "
                            f"Pick the one that matches this environment's deployment context."
                        ) if len(templates) > 1 else None,
                    })
        else:
            if resource_type not in unknown:
                unknown.append(resource_type)

    return {
        "analyzed_file": str(target),
        "dependency_count": len(deps),
        "dependencies": deps,
        "unrecognised_data_sources": unknown,
        "azapi_data_sources": azapi_data_sources,
        "note": (
            "Deploy dependencies FIRST (bottom-up order). "
            "Each dependency may have its own dependencies — check recursively. "
            "For ambiguous entries, pick the template that fits the current deployment context. "
            "azapi_data_sources are azapi-specific lookups — inspect the main.tf `type` attribute "
            "for the actual ARM resource type used."
        ),
    }


# ── Tool 4: generate_tfvars_template ─────────────────────────────────────────

def generate_tfvars_template(path: str) -> dict:
    """
    Parse a variables.tf file (or directory containing one) and generate a
    ready-to-paste terraform.tfvars file with all variables, their types,
    descriptions and <REPLACE_ME> placeholders.

    Args:
        path: Path to a variables.tf file or the template directory containing it.
    """
    target = Path(path) if Path(path).is_absolute() else Path(".") / path
    if target.is_dir():
        target = target / "variables.tf"

    if not target.exists():
        return {"error": f"variables.tf not found at: {target}"}

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    # Parse each variable block (greedy multi-line)
    var_blocks = re.findall(r'variable\s+"([^"]+)"\s*\{([^}]+)\}', content, re.DOTALL)

    variables = []
    for var_name, body in var_blocks:
        type_m    = re.search(r'type\s*=\s*(.+?)[\n#]', body + "\n")
        desc_m    = re.search(r'description\s*=\s*"([^"]*)"', body)
        default_m = re.search(r'default\s*=\s*(.+?)[\n#]', body + "\n")
        sensitive_m = re.search(r'sensitive\s*=\s*true', body)

        var_type    = type_m.group(1).strip()    if type_m    else "string"
        var_desc    = desc_m.group(1)            if desc_m    else ""
        var_default = default_m.group(1).strip() if default_m else None
        is_sensitive = bool(sensitive_m) or any(s in var_name.lower() for s in _SENSITIVE_NAMES)
        is_required  = var_default is None

        variables.append({
            "name": var_name, "type": var_type, "description": var_desc,
            "default": var_default, "required": is_required, "sensitive": is_sensitive,
        })

    # Build the tfvars file content
    lines = [
        "# terraform.tfvars",
        "# Fill in your values. NEVER commit this file to version control.",
        "# Sensitive values marked ⚠️  — store those in a separate secure file.",
        "",
    ]

    required = [v for v in variables if v["required"]]
    optional = [v for v in variables if not v["required"]]

    if required:
        lines.append("# ════════════════════════════════════════")
        lines.append("# REQUIRED  (no default — must be provided)")
        lines.append("# ════════════════════════════════════════")
        for v in required:
            if v["description"]:
                lines.append(f"# {v['description']}")
            lines.append(f"# type: {v['type']}")
            if v["sensitive"]:
                lines.append("# ⚠️  SENSITIVE — keep private")
            placeholder = '"<REPLACE_ME>"' if "string" in v["type"] else "<REPLACE_ME>"
            lines.append(f'{v["name"]} = {placeholder}')
            lines.append("")

    if optional:
        lines.append("# ════════════════════════════════════════")
        lines.append("# OPTIONAL  (defaults shown — change if needed)")
        lines.append("# ════════════════════════════════════════")
        for v in optional:
            if v["description"]:
                lines.append(f"# {v['description']}")
            lines.append(f"# type: {v['type']}")
            lines.append(f'{v["name"]} = {v["default"]}')
            lines.append("")

    return {
        "analyzed_file": str(target),
        "variable_count": len(variables),
        "required_count": len(required),
        "optional_count": len(optional),
        "tfvars_content": "\n".join(lines),
        "variables": variables,
    }


# ── Tool 5: search_templates ──────────────────────────────────────────────────

def search_templates(keyword: str) -> dict:
    """
    Full-text search across all Terraform template README files and variable
    descriptions for a keyword. Returns matching templates with context snippets.
    Much faster than reading every README one by one.

    Args:
        keyword: Word or phrase to search for (case-insensitive).
    """
    base = Path("./terraform")
    if not base.exists():
        return {"error": "terraform/ directory not found"}

    keyword_lower = keyword.lower()
    results = []
    seen_paths: set[str] = set()

    for search_file in sorted(base.rglob("*.md")) :
        template_dir = str(search_file.parent)
        try:
            content = search_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if keyword_lower not in content.lower():
            continue

        snippets = []
        for line in content.splitlines():
            if keyword_lower in line.lower():
                stripped = line.strip()
                if stripped and stripped not in snippets:
                    snippets.append(stripped)
                if len(snippets) >= 3:
                    break

        if template_dir not in seen_paths:
            seen_paths.add(template_dir)
            results.append({
                "template_path": template_dir,
                "matched_in": str(search_file),
                "snippets": snippets,
            })

    # Also search variables.tf descriptions not already found
    for vars_file in sorted(base.rglob("variables.tf")):
        template_dir = str(vars_file.parent)
        if template_dir in seen_paths:
            continue
        try:
            content = vars_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if keyword_lower not in content.lower():
            continue

        snippets = []
        for line in content.splitlines():
            if keyword_lower in line.lower():
                stripped = line.strip()
                if stripped and stripped not in snippets:
                    snippets.append(stripped)
                if len(snippets) >= 3:
                    break

        seen_paths.add(template_dir)
        results.append({
            "template_path": template_dir,
            "matched_in": str(vars_file),
            "snippets": snippets,
        })

    return {
        "keyword": keyword,
        "match_count": len(results),
        "results": results,
        "note": "Read the README.md of each matched template for full details.",
    }
