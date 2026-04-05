"""
bundle_tools.py — Deployment bundle packager

Takes the LLM's deployment plan (ordered list of steps with template paths and
tfvars content) and packages them into a downloadable zip file.

The LLM never touches .tf file content — it only passes:
  - The template paths it identified
  - The tfvars strings already produced by generate_tfvars_template()

The tool copies the actual policy-compliant .tf files from the project and
combines them with the customer's variable values into a ready-to-use bundle.

Bundle layout:
  bundle_<id>.zip
    ├── README.txt                      ← deployment order + commands
    ├── config/                         ← shared config module (if used by any step)
    │     ├── main.tf
    │     ├── output.tf
    │     └── azapi_api_output.tf
    └── deploy/
          ├── step1_<label>/
          │     ├── main.tf             ← copied as-is from project
          │     ├── variables.tf
          │     ├── outputs.tf
          │     ├── provider.tf         ← source = "../../config" resolves correctly
          │     └── terraform.tfvars    ← customer values from LLM
          ├── step2_<label>/
          │     └── ...
          └── step3_<label>/
                └── ...

WHY the deploy/ nesting?
  Templates reference the shared config module as: source = "../../config"
  Placing steps under deploy/ means:
    deploy/stepN_label/  →  ../../  →  bundle root  →  bundle root/config/ ✓
  Without this nesting the relative path would escape the bundle entirely.
"""
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger

# Bundle storage — ephemeral, lives for the process lifetime
# In production swap for object storage (Azure Blob, S3, etc.)
_BUNDLES_DIR = Path("./tmp/bundles")

# .tf files to copy per template (provider.tf + README.md included so bundle is self-contained)
_TEMPLATE_FILES = {"main.tf", "variables.tf", "outputs.tf", "provider.tf", "README.md"}

# Matches:  module "any_name" { ... source = "./relative/path" ... }
# Captures the source string value. Skips registry sources (no leading dot).
_MODULE_BLOCK_RE = re.compile(
    r'module\s+"[^"]+"\s*\{[^}]*?source\s*=\s*"([^"]+)"',
    re.DOTALL,
)


def _find_module_sources(src_dir: Path) -> dict[str, Path]:
    """
    Scan all .tf files in src_dir for relative module source declarations.

    Returns {bundle_dest_name: resolved_absolute_path} for every relative
    module source found.  Registry sources (e.g. "hashicorp/consul/aws")
    are skipped — Terraform downloads those during `terraform init`.

    Bundle placement strategy
    ─────────────────────────
    Steps live at  deploy/stepN_label/  (depth 2 from bundle root).
    From there, "../../X" always resolves to bundle_root/X.
    So we strip the relative traversal and use only the final path
    component(s) after the last "../" as the bundle-level destination.

    Example:
      source = "../../config"   →  resolved = /abs/path/terraform/config
                                →  dest_name = "config"
                                →  bundle path = bundle_root/config/     ✓
      source = "../../shared/networking"
                                →  dest_name = "shared/networking"
                                →  bundle path = bundle_root/shared/networking/  ✓
    """
    modules: dict[str, Path] = {}  # dest_name → absolute resolved path

    for tf_file in src_dir.glob("*.tf"):
        try:
            content = tf_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for source in _MODULE_BLOCK_RE.findall(content):
            if not source.startswith("."):
                # Registry or absolute path — Terraform handles these itself
                continue

            resolved = (src_dir / source).resolve()
            if not resolved.exists():
                logger.warning(f"Module source '{source}' in {tf_file} resolved to {resolved} — not found, skipping")
                continue

            # Derive the bundle destination name by stripping leading "../" segments.
            # e.g. "../../config" → "config",  "../../shared/net" → "shared/net"
            clean = source.lstrip("./").lstrip("/")
            # Remove any remaining leading "../" traversal artefacts
            while clean.startswith("../"):
                clean = clean[3:]
            dest_name = clean or resolved.name

            if dest_name in modules and modules[dest_name] != resolved:
                logger.warning(
                    f"Module name collision: '{dest_name}' maps to both "
                    f"{modules[dest_name]} and {resolved}. Using first."
                )
                continue

            modules[dest_name] = resolved

    return modules


def bundle_deployment_plan(steps: list[dict]) -> dict:
    """
    Package a deployment plan into a downloadable zip bundle.

    Call this as the FINAL step of every deployment plan, after you have:
      1. Identified all required templates and their deployment order
      2. Called generate_tfvars_template() for each step

    Args:
        steps: Ordered list of deployment steps. Each step is a dict with:
            step_number   (int)  — 1-based ordering
            label         (str)  — human-readable name, e.g. "Resource Group"
            template_path (str)  — path to template dir, e.g. "terraform/resource_group/create/"
            tfvars_content (str) — full terraform.tfvars content from generate_tfvars_template()

    Returns:
        bundle_id    — unique identifier for the bundle
        download_url — URL to pass to the customer: GET /api/download/<bundle_id>
        steps_packaged — number of steps successfully packaged
        errors       — list of any per-step errors (missing files etc.)
    """
    if not steps:
        return {"error": "No steps provided — nothing to bundle."}

    bundle_id  = uuid.uuid4().hex[:12]
    bundle_dir = _BUNDLES_DIR / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Steps are nested under deploy/ so that the relative path "../../config"
    # written in every provider.tf correctly resolves to bundle_root/config/.
    #   deploy/stepN_label/  →  ../../  →  bundle_root/  →  bundle_root/config/ ✓
    deploy_dir = bundle_dir / "deploy"
    deploy_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    packaged  = 0
    modules_to_include: dict[str, Path] = {}  # dest_name → resolved abs path
    step_dirs: list[tuple[int, str, Path]] = []   # (step_number, label, dir_path)

    for step in steps:
        step_num      = step.get("step_number", 0)
        label         = step.get("label", f"step{step_num}")
        template_path = step.get("template_path", "")
        tfvars        = step.get("tfvars_content", "")

        # Sanitise label for use as a directory name
        safe_label = label.lower().replace(" ", "_").replace("/", "_")
        step_dir_name = f"step{step_num}_{safe_label}"
        step_dir = deploy_dir / step_dir_name
        step_dir.mkdir(parents=True, exist_ok=True)

        # Copy .tf + README files from the project template
        src_dir = Path(template_path) if Path(template_path).is_absolute() else Path(".") / template_path
        if not src_dir.exists():
            msg = f"Step {step_num}: template path not found: {template_path}"
            errors.append(msg)
            logger.warning(msg)
            continue

        copied = 0
        for tf_file in src_dir.iterdir():
            if tf_file.is_file() and tf_file.name in _TEMPLATE_FILES:
                shutil.copy2(tf_file, step_dir / tf_file.name)
                copied += 1

        if copied == 0:
            msg = f"Step {step_num}: no .tf files found in {template_path}"
            errors.append(msg)
            logger.warning(msg)
            continue

        # Write customer tfvars
        if tfvars:
            (step_dir / "terraform.tfvars").write_text(tfvars, encoding="utf-8")
        else:
            errors.append(f"Step {step_num}: no tfvars_content provided — terraform.tfvars not written")

        # Discover all relative module sources used by this step and accumulate them
        for dest_name, resolved in _find_module_sources(src_dir).items():
            if dest_name not in modules_to_include:
                modules_to_include[dest_name] = resolved

        step_dirs.append((step_num, label, step_dir))
        packaged += 1

    if packaged == 0:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        return {"error": "No steps could be packaged. Check template paths.", "errors": errors}

    # Copy every discovered local module into the bundle root.
    # Steps are at deploy/stepN/ (depth 2), so "../../<dest_name>" resolves to bundle_root/<dest_name>.
    modules_included: list[str] = []
    for dest_name, resolved in modules_to_include.items():
        dest_path = bundle_dir / dest_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(resolved, dest_path)
        modules_included.append(dest_name)
        logger.info(f"Bundle {bundle_id}: module '{dest_name}' included from {resolved}")

    # Write top-level README.txt with ordered deployment instructions
    readme_lines = [
        "Azure Self-Service Deployment Bundle",
        "=" * 40,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Bundle ID: {bundle_id}",
        "",
        "STRUCTURE",
        "-" * 40,
    ]
    for mod_name in sorted(modules_included):
        readme_lines.append(f"{mod_name}/          ← shared Terraform module (auto-included)")
    readme_lines += [
        "deploy/          ← one sub-directory per deployment step",
        "",
        "IMPORTANT",
        "-" * 40,
        "1. Review ALL terraform.tfvars files before running — fill in any <REPLACE_ME> values.",
        "2. Sensitive values (subscription_id, tenant_id, client_id, client_secret) must be",
        "   placed in a separate terraform.tfvars.sensitive file — NEVER commit them to git.",
        "3. Run steps in ORDER — each step depends on the previous one being complete.",
        "4. Run each terraform command from INSIDE the step directory (cd deploy/stepN_...).",
        "5. Before running terraform apply, verify NO <REPLACE_ME> placeholders remain:",
        "     grep -r '<REPLACE_ME>' deploy/",
        "   terraform apply will fail with confusing errors if any placeholder is left unfilled.",
        "6. OUTPUT WIRING — each step prints output values after a successful apply (e.g.",
        "   resource_group_name, vnet_id, subnet_id). Copy these into the next step's",
        "   terraform.tfvars where indicated. Check each step's variables.tf — variables",
        "   whose description says 'output from <previous step>' need this manual wiring.",
        "",
        "DEPLOYMENT ORDER",
        "-" * 40,
    ]
    for step_num, label, step_dir in sorted(step_dirs, key=lambda x: x[0]):
        dir_name = step_dir.name
        readme_lines += [
            "",
            f"Step {step_num} — {label}",
            f"  cd deploy/{dir_name}",
            "  terraform init",
            "  terraform plan -var-file=terraform.tfvars",
            "  terraform apply -var-file=terraform.tfvars",
            "  cd ../..",
        ]

    readme_lines += [
        "",
        "-" * 40,
        "Templates in this bundle are company-approved and policy-compliant.",
        "Do not modify .tf files — only edit terraform.tfvars.",
    ]
    (bundle_dir / "README.txt").write_text("\n".join(readme_lines), encoding="utf-8")

    # Zip the bundle directory
    zip_path = _BUNDLES_DIR / f"bundle_{bundle_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(bundle_dir.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(bundle_dir))

    # Clean up the unzipped staging directory
    shutil.rmtree(bundle_dir, ignore_errors=True)

    logger.info(f"Bundle {bundle_id}: {packaged} steps packaged → {zip_path}")

    return {
        "bundle_id":        bundle_id,
        "download_url":     f"/api/download/{bundle_id}",
        "steps_packaged":   packaged,
        "modules_included": modules_included,
        "errors":           errors,
        "message": (
            f"Bundle ready. Tell the customer to download it from: /api/download/{bundle_id} "
            f"Then unzip and follow README.txt for the deployment order and commands."
        ),
    }


def get_bundle_path(bundle_id: str) -> Path | None:
    """Return the zip path for a bundle_id, or None if not found."""
    p = _BUNDLES_DIR / f"bundle_{bundle_id}.zip"
    return p if p.exists() else None
