"""Read-only invoice reconciliation change report processor."""

from invoice_change_adapter import compare_existing_invoices
from invoice_change_breakdown import build_change_breakdown
from invoice_source_schema import invoice_number


def generate_change_report(existing_rows, uploaded_rows):
    """Compare complete existing invoice data with uploaded invoices."""

    existing_rows = list(existing_rows)
    uploaded_rows = list(uploaded_rows)

    comparison = compare_existing_invoices(
        existing_rows,
        uploaded_rows,
    )

    breakdown = build_change_breakdown(comparison)

    if comparison["summary"]["total"] != len(uploaded_rows):
        raise ValueError("Invoice comparison total mismatch")

    if breakdown["total_invoices"] != len(uploaded_rows):
        raise ValueError("Report breakdown total mismatch")

    return {
        "version": "1.0.0",
        "mode": "READ_ONLY",
        "reconciliation_executed": False,
        "database_changed": False,
        "summary": comparison["summary"],
        "report_breakdown": breakdown["report_breakdown"],
        "unclassified": breakdown["unclassified"],
        "details": comparison["details"],
    }
