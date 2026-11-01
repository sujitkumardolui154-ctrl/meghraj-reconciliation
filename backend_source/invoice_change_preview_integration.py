"""Read-only upload comparison integration."""

from collections import Counter

from invoice_excel_parser import parse_excel
from invoice_change_service import preview_invoice_changes
from invoice_source_schema import invoice_number


def build_change_audit(db, filename, data):
    parsed = parse_excel(filename, data)

    valid_rows = parsed["rows"]
    rejected_rows = parsed["rejected"]

    report = preview_invoice_changes(db, valid_rows)

    details = list(report["details"])

    for row in rejected_rows:
        details.append({
            "invoice_no": row.get("invoice_no", ""),
            "source_row": row.get("source_row"),
            "tag": "CONFLICT",
            "old_payment": None,
            "new_payment": None,
            "previous_report": None,
            "balance_review": False,
            "reason": ",".join(row.get("reasons", [])),
        })

    counts = Counter(row["tag"] for row in details)

    total = len(valid_rows) + len(rejected_rows)

    if len(details) != total:
        raise ValueError("Change audit row-count mismatch")

    return {
        "version": "1.0.0",
        "mode": "READ_ONLY",
        "database_changed": False,
        "reconciliation_executed": False,
        "total": total,
        "summary": dict(counts),
        "details": details,
    }
