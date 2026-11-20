"""Workstream D combined financial engine RELEASE GATE — no financial execution.

This is a capability/evidence gate, not the canonical payment allocator.
Do not use as a substitute for the private approved reconciliation engine.
"""
from collections.abc import Mapping

REQUIRED_CAPABILITIES = (
    "canonical_financial_engine_source",
    "invoice_schema_53_parity",
    "sol_branch_master_integrity",
    "same_sol_full_and_partial_allocation",
    "service_period_month_year_matching",
    "sbisa_sol_1_allocation",
    "tds_decimal_half_up_rules",
    "payment_duplicate_and_conflict_hold",
    "credit_note_correction_hold",
    "gst_v2_7_original_invoice_parity",
    "financial_source_to_output_value_parity",
    "authenticated_readonly_workspace_access",
    "no_financial_writes",
    "aws_immutable_image_provenance",
    "staging_backup_and_rollback",
)

class FinancialEngineNotReady(RuntimeError):
    pass


def assess_combined_readiness(evidence):
    """Only explicitly independently certified gates can pass.

    Expected evidence records are dicts with status exactly PASS,
    reviewer and nonempty immutable evidence_ref. No caller bool
    or generic CI success can be promoted to financial parity.
    """
    if not isinstance(evidence, Mapping):
        raise ValueError("EVIDENCE_MAP_REQUIRED")
    checks = {}
    for name in REQUIRED_CAPABILITIES:
        record = evidence.get(name)
        approved = (
            isinstance(record, Mapping)
            and record.get("status") == "PASS"
            and isinstance(record.get("reviewer"), str)
            and bool(record["reviewer"].strip())
            and isinstance(record.get("evidence_ref"), str)
            and bool(record["evidence_ref"].strip())
        )
        checks[name] = "PASS" if approved else "BLOCKED"
    blocked = [name for name in REQUIRED_CAPABILITIES if checks[name] != "PASS"]
    return {
        "status": "CANDIDATE_REVIEW_READY" if not blocked else "BLOCKED",
        "checks": checks,
        "blocked_capabilities": blocked,
        "production_financial_cutover": "BLOCKED",
        "financial_write_performed": False,
        "approved_for_settlement": False,
        "deployment_performed": False,
    }


def require_combined_staging_readiness(evidence):
    result = assess_combined_readiness(evidence)
    if result["blocked_capabilities"]:
        raise FinancialEngineNotReady(
            "COMBINED_ENGINE_GATES_BLOCKED:" + ",".join(result["blocked_capabilities"])
        )
    return result
