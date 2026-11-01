"""Read-only reconciliation change comparison service."""

from report_api import load_report_rows_v142
from invoice_change_report import generate_change_report


def preview_invoice_changes(db, uploaded_rows):
    """
    Compare uploaded invoices against the verified baseline
    and completed imported invoices.

    No Firestore writes or financial settlement operations.
    """

    baseline, imported = load_report_rows_v142(db)

    existing = baseline + imported

    report = generate_change_report(
        existing,
        uploaded_rows,
    )

    if report["summary"]["total"] != len(uploaded_rows):
        raise ValueError("Invoice comparison count mismatch")

    if report["database_changed"] is not False:
        raise ValueError("Read-only contract violated")

    if report["reconciliation_executed"] is not False:
        raise ValueError("Financial execution is prohibited")

    return report
