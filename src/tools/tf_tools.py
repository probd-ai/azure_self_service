"""
tf_tools.py — Phase 2 tools (stubs, ready to implement when provisioning is needed)
"""


def terraform_plan(service_path: str, variables: dict) -> dict:
    """
    Run `terraform plan` for a given service template with provided variable values.
    Returns the plan output for customer review before applying.
    """
    # TODO Phase 2: run subprocess terraform plan with -var flags
    raise NotImplementedError("Provisioning (Phase 2) not yet implemented.")


def terraform_apply(service_path: str, variables: dict, job_id: str) -> dict:
    """
    Run `terraform apply` after customer approval.
    Returns a job_id to poll for status.
    """
    # TODO Phase 2: run subprocess terraform apply, track job async
    raise NotImplementedError("Provisioning (Phase 2) not yet implemented.")


def get_deployment_status(job_id: str) -> dict:
    """
    Poll the status of a running terraform job.
    """
    # TODO Phase 2: check subprocess / background job status
    raise NotImplementedError("Provisioning (Phase 2) not yet implemented.")
