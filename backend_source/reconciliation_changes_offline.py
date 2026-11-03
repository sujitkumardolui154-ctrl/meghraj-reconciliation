"""Offline SBI reconciliation-change report from two independently supplied snapshots.

Strictly classification-only: no Firestore access, payment allocation,
reconciliation engine execution, finance calculations, or external calls.
No irreversible invoice/payment statuses are generated. The output is private
financial data; never commit generated reports to GitHub or public dashboards.
"""
from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
import io

INVOICE = "invoice_no"
PAYMENT = "payment_received"
STATUS = "reconciliation_status"

CATEGORIES = (
    "NEW", "UNCHANGED", "PAYMENT_ADDED", "PAYMENT_CHANGED",
    "PAYMENT_CLEARED_REVIEW", "CONFLICT",
)
CSV_HEADERS = (
    "Invoice No", "Change Type", "Old Payment Received",
    "New Payment Received", "Old Reconciliation Status",
    "New Reconciliation Status", "Old Row Count", "New Row Count",
    "Review Reason",
)


def _index(rows):
    if not isinstance(rows, list):
        raise ValueError("Snapshot must be an explicit list")
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or any(
                key not in row or not isinstance(row[key], str)
                for key in (INVOICE, PAYMENT, STATUS)):
            raise ValueError("Invalid reconciliation snapshot row")
        key = row[INVOICE].strip()
        if not key:
            raise ValueError("Missing invoice number; reconciliation comparison refused")
        indexed.setdefault(key, []).append(row)
    return indexed


def _amount(text):
    """Return (valid, amount-or-None) without silently treating text as credit."""
    value = text.strip()
    if value == "":
        return True, None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False, None
    if not number.is_finite() or number < 0:
        return False, None
    return True, None if number == 0 else number


def _classify(before, after):
    if before is None and after is not None:
        valid, _ = _amount(after[PAYMENT])
        return ("NEW", "" if valid else "NEW_NON_NUMERIC_PAYMENT_REVIEW")
    if before is not None and after is None:
        return "CONFLICT", "INVOICE_MISSING_FROM_NEW_SNAPSHOT"
    old_ok, old_num = _amount(before[PAYMENT])
    new_ok, new_num = _amount(after[PAYMENT])
    if not old_ok or not new_ok:
        return "CONFLICT", "NON_NUMERIC_OR_NEGATIVE_PAYMENT"
    if old_num == new_num:
        if before[STATUS] == after[STATUS]:
            return "UNCHANGED", ""
        return "CONFLICT", "STATUS_CHANGED_WITHOUT_PAYMENT_CHANGE"
    if old_num is None and new_num is not None:
        return "PAYMENT_ADDED", ""
    if old_num is not None and new_num is None:
        return "PAYMENT_CLEARED_REVIEW", "PREVIOUS_PAYMENT_NOW_BLANK_OR_ZERO"
    return "PAYMENT_CHANGED", ""


def make_reconciliation_change_report(old_rows, new_rows):
    """Return immutable logical diff; originals are never modified.

    Duplicate invoice keys are CONFLICT, never arbitrarily allocated to one row.
    """
    old = _index(old_rows)
    new = _index(new_rows)
    output = []
    for invoice in sorted(set(old) | set(new)):
        prev = old.get(invoice, [])
        curr = new.get(invoice, [])
        if len(prev) > 1 or len(curr) > 1:
            kind, reason = "CONFLICT", "DUPLICATE_INVOICE_NUMBER"
        else:
            kind, reason = _classify(prev[0] if prev else None, curr[0] if curr else None)
        a = prev[0] if len(prev) == 1 else None
        b = curr[0] if len(curr) == 1 else None
        output.append({
            "invoice_no": invoice,
            "category": kind,
            "old_payment": a[PAYMENT] if a else "",
            "new_payment": b[PAYMENT] if b else "",
            "old_status": a[STATUS] if a else "",
            "new_status": b[STATUS] if b else "",
            "old_count": len(prev),
            "new_count": len(curr),
            "review_reason": reason,
        })
    counts = Counter(row["category"] for row in output)
    return output, {
        "total_invoice_groups": len(output),
        "categories": {name: counts[name] for name in CATEGORIES},
        "review_required": bool(counts["PAYMENT_CLEARED_REVIEW"] or counts["CONFLICT"]),
        "source_rows_mutated": False,
        "financial_execution": "RESTRICTED",
        "approved_for_settlement": False,
        "source_snapshot_certified": False,
    }


def _csv_cell(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def change_report_csv(rows):
    """Produce an optional private UTF-8-BOM CSV; do not publish this CSV."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(CSV_HEADERS)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid change report row")
        writer.writerow(_csv_cell(row[key]) for key in (
            "invoice_no", "category", "old_payment", "new_payment",
            "old_status", "new_status", "old_count", "new_count",
            "review_reason",
        ))
    return out.getvalue().encode("utf-8-sig")
