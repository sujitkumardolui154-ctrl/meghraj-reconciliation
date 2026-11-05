"""Owner-approved report-only invoice exception routing (2026-11-05).

Read-only classification. Never modifies source invoice rows, allocation records
or the frozen 53-column CSV headers. A repeated invoice number is NOT proof
of multiple payment allocations.
"""

FORCED_ERROR_INVOICES = frozenset({"MXP/2025-2026-04"})
CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES = frozenset({
    "MXP10092", "MXP10565", "MXP10566", "MXP9014",
})


def invoice_report_error_reason(row):
    """Return a report exception reason or None.

    All invoice numbers are eligible for error routing on explicit, verified
    multiple allocations, reconciliation stages or conflicts. Duplicate invoice
    numbers and credit-note narration alone are not evidence of these events.
    Unverified evidence never clears any existing error.
    """
    if not isinstance(row, dict):
        raise ValueError("Invoice report row must be a dictionary")
    invoice = row.get("invoice_no")
    if not isinstance(invoice, str):
        raise ValueError("Original invoice number is unavailable")
    invoice = invoice.strip()

    if invoice in FORCED_ERROR_INVOICES:
        return "OWNER_FLAGGED_INVOICE_COUNT_ERROR"

    # Apply the same rule to ANY invoice: verified multi-allocation or
    # multi-stage reconciliation warrants Error Report review.
    allocation_count = row.get("verified_allocation_count")
    if (row.get("allocation_verification") == "VERIFIED"
            and type(allocation_count) is int and allocation_count > 1):
        return "VERIFIED_MULTIPLE_ALLOCATION"

    stage_count = row.get("verified_reconciliation_stage_count")
    if (row.get("reconciliation_stage_verification") == "VERIFIED"
            and type(stage_count) is int and stage_count > 1):
        return "VERIFIED_MULTISTAGE_RECONCILIATION"

    # Only an affirmative, explicitly verified conflict is actionable;
    # missing/unknown conflict status is not proof of a conflict.
    if (row.get("conflict_verification") == "VERIFIED"
            and row.get("reconciliation_conflict") is True):
        return "VERIFIED_RECONCILIATION_CONFLICT"
    return None


def route_payment_report(row, original_kind):
    """Route only evidenced exceptions into the existing Error Value report."""
    if original_kind not in ("unpaid", "ok", "error-value"):
        raise ValueError("Unsupported payment report category")
    reason = invoice_report_error_reason(row)
    return ("error-value" if reason else original_kind), reason


def exception_evidence_coverage(rows):
    """Aggregate only: never exposes invoice identifiers or financial values.

    Use these counts to avoid presenting unverified exception detection as
    completed live reconciliation screening.
    """
    from collections import Counter

    counts = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid source row in evidence coverage")
        counts["total_rows"] += 1
        if row.get("allocation_verification") == "VERIFIED":
            counts["verified_allocation_evidence_rows"] += 1
        if row.get("reconciliation_stage_verification") == "VERIFIED":
            counts["verified_stage_evidence_rows"] += 1
        if row.get("conflict_verification") == "VERIFIED":
            counts["verified_conflict_evidence_rows"] += 1
        reason = invoice_report_error_reason(row)
        if reason:
            counts["rule_routed_error_rows"] += 1
    return {
        key: counts[key] for key in (
            "total_rows",
            "verified_allocation_evidence_rows",
            "verified_stage_evidence_rows",
            "verified_conflict_evidence_rows",
            "rule_routed_error_rows",
        )
    }
