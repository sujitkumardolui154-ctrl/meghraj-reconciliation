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

    A conditional invoice is escalated only on explicit, verified allocation
    evidence from an authorized source, not on a duplicate invoice number or
    credit-note narration. Unverified evidence never clears any existing error.
    """
    if not isinstance(row, dict):
        raise ValueError("Invoice report row must be a dictionary")
    invoice = row.get("invoice_no")
    if not isinstance(invoice, str):
        raise ValueError("Original invoice number is unavailable")
    invoice = invoice.strip()

    if invoice in FORCED_ERROR_INVOICES:
        return "OWNER_FLAGGED_INVOICE_COUNT_ERROR"

    if invoice in CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES:
        count = row.get("verified_allocation_count")
        verified = row.get("allocation_verification") == "VERIFIED"
        if verified and type(count) is int and count > 1:
            return "VERIFIED_MULTIPLE_ALLOCATION"
    return None


def route_payment_report(row, original_kind):
    """Route only evidenced exceptions into the existing Error Value report."""
    if original_kind not in ("unpaid", "ok", "error-value"):
        raise ValueError("Unsupported payment report category")
    reason = invoice_report_error_reason(row)
    return ("error-value" if reason else original_kind), reason
