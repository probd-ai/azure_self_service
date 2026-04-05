"""
index_builder.py — Terraform template index builder

Builds terraform/_index.json — a lightweight navigation MAP for the LLM.
The map contains: path, service, template_type, mandate_read_files per template.

The LLM reads the map to know WHAT EXISTS and WHERE FILES ARE.
The LLM reads the actual files to reason about dependencies, variables, and plans.

Two public LLM tools:
  get_template_index() — returns terraform/_index.json
  rebuild_index()      — force full re-scan (call if templates change at runtime)

Called at startup from src/api/main.py via build_index().
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

# ── Paths ─────────────────────────────────────────────────────────────────────
_TERRAFORM_BASE = Path("./terraform")
_INDEX_PATH     = Path("./terraform/_index.json")
_CONFIG_DIR     = Path("./terraform/config")


# ══════════════════════════════════════════════════════════════════════════════
# Navigation index builder
# ══════════════════════════════════════════════════════════════════════════════

def _is_template_dir(path: Path) -> bool:
    """A valid template directory has both main.tf and variables.tf."""
    return (path / "main.tf").exists() and (path / "variables.tf").exists()


def _list_files(directory: Path) -> list[str]:
    """Return sorted POSIX-style relative paths for all files in a directory."""
    return [f.as_posix() for f in sorted(directory.iterdir()) if f.is_file()]


def _build_navigation_index() -> dict:
    """
    Walk terraform/ and build the LLM navigation map.
    Skips: config/ (handled separately), any dir starting with '_'.
    """
    templates = []

    for service_dir in sorted(_TERRAFORM_BASE.iterdir()):
        if not service_dir.is_dir():
            continue
        if service_dir.name.startswith("_") or service_dir.name == "config":
            continue

        for template_dir in sorted(service_dir.iterdir()):
            if not template_dir.is_dir() or not _is_template_dir(template_dir):
                continue

            templates.append({
                "path":               template_dir.as_posix() + "/",
                "service":            service_dir.name,
                "template_type":      template_dir.name,
                "mandate_read_files": _list_files(template_dir),
            })

    config_files = _list_files(_CONFIG_DIR) if _CONFIG_DIR.exists() else []

    return {
        "WARNING": (
            "Navigation map only — not source of truth. "
            "For EVERY template in a deployment plan you MUST read ALL files listed in "
            "mandate_read_files AND all files in config_module.mandate_read_files before "
            "presenting anything to the customer. "
            "Never plan, guess dependencies, or list variables from this index alone. "
            "The files are always right."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_module": {
            "path": "terraform/config/",
            "note": (
                "Shared config module inherited by ALL templates via module.config. "
                "Always read these files alongside any template you are planning."
            ),
            "mandate_read_files": config_files,
        },
        "templates": templates,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Public build function — called at startup and by rebuild_index() tool
# ══════════════════════════════════════════════════════════════════════════════

def build_index() -> dict:
    """
    Scan all terraform templates and write terraform/_index.json.

    The index is a navigation MAP only:
      path / service / template_type / mandate_read_files per template.

    The LLM reads the index to discover what exists and which files to read.
    All dependency resolution, variable inspection, and planning is done by
    the LLM reading the actual files — not from this index.

    Returns a summary dict.
    """
    if not _TERRAFORM_BASE.exists():
        return {"error": "terraform/ directory not found"}

    index = _build_navigation_index()

    try:
        _INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
        logger.info(f"Wrote {_INDEX_PATH} — {len(index['templates'])} templates indexed")
    except Exception as e:
        return {"error": f"Could not write index file: {e}"}

    return {
        "status":            "ok",
        "templates_indexed": len(index["templates"]),
        "index_path":        str(_INDEX_PATH),
        "message":           "Navigation index rebuilt successfully.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# LLM-facing tool functions
# ══════════════════════════════════════════════════════════════════════════════

def get_template_index() -> dict:
    """
    Returns the terraform navigation index.
    Auto-builds it if it does not exist yet (e.g. first call after clean checkout).
    """
    if not _INDEX_PATH.exists():
        result = build_index()
        if "error" in result:
            return result
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"Could not read index: {e}"}


def rebuild_index() -> dict:
    """
    Force a full re-scan of all terraform templates.
    Use this if templates were added, removed, or modified since startup.
    Rebuilds both the navigation index JSON and the in-memory resource type map.
    """
    return build_index()
