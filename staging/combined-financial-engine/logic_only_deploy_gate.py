"""SBI owner deployment policy: LOGIC-ONLY with synthetic-only test execution.

A *declaration gate* to fail closed on prohibited deployment plans.
This cannot establish host/runtime isolation by itself; independent
CI, IAM/network/security checks are mandatory before any actual deploy.
No finance sources, files, databases or cloud APIs are opened here.
"""
from collections.abc import Mapping

REQUIRED = {
    "deployment_mode": "LOGIC_ONLY",
    "test_source": "SYNTHETIC_ONLY",
    "deploy_approved_rules_and_logic_only": True,
    "historical_invoice_reads": False,
    "historical_payment_reads": False,
    "historical_credit_note_reads": False,
    "historical_gst_reads": False,
    "historical_financial_calculations": False,
    "reconciliation_replay": False,
    "automatic_backfill": False,
    "database_migration": False,
    "existing_allocation_mutation": False,
    "prior_status_changes": False,
    "financial_write_permission": False,
    "legacy_finance_database_connection": False,
    "existing_financial_source_mounts": False,
    "auto_process_old_evidence": False,
    "production_traffic_change": False,
}

class LogicOnlyPolicyBlocked(RuntimeError):
    pass


def check_logic_only_manifest(manifest):
    """Validate an explicit plan. Never infer safety from missing properties.

    This is necessary source-policy QA, NOT proof a runtime is isolated.
    Untrusted/self-declared plans do not authorize deployment.
    """
    if not isinstance(manifest, Mapping):
        raise LogicOnlyPolicyBlocked("DEPLOYMENT_POLICY_MANIFEST_REQUIRED")
    violations = [k for k, expected in REQUIRED.items()
                  if type(manifest.get(k)) is not type(expected)
                  or manifest.get(k) != expected]
    for key in ("existing_finance_data_paths", "historical_backfill_jobs",
                "financial_database_endpoints"):
        if not isinstance(manifest.get(key), list) or manifest[key]:
            violations.append(key)
    if violations:
        raise LogicOnlyPolicyBlocked(
            "OWNER_LOGIC_ONLY_POLICY_VIOLATED:" + ",".join(sorted(violations)))
    return {
        "status": "SOURCE_POLICY_CONTRACT_PASS_ONLY",
        "owner_instruction": "DEPLOY_APPROVED_RULES_LOGIC_ONLY",
        "test_source": "SYNTHETIC_ONLY",
        "historical_data_read": False,
        "historical_data_recomputed": False,
        "historical_data_modified": False,
        "production_deployed": False,
        "financial_write_performed": False,
        "host_isolation_verified": False,
    }
