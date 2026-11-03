"""A02 approved v2.18 PAYMNENT report audit; explicitly NOT a settlement engine.

Only an already-classified 23-column PAYMNENT v2.18 snapshot may be filtered.
This code NEVER infers SUSPENSE from invoice Column U, blank credits, balances,
narration or amount similarity. Original bank columns A:L are immutable.
Master v2.51 / Matrix v2.39 still require independent QA and Finance release.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import io

# OUT-SCHEMA-V218-001, approved 2026-10-28. Exact order and spelling.
PAYMENT_HEADERS = [
    "Location", "Branch Name", "Txn Date", "Value Date",
    "Description", "Branch Code", "Name", "        Debit",
    "Credit", "Balance", "Record For Me", "",
    "Model Reconciliation Status", "Model Reconciliation Remarks",
    "Model Invoice No (Candidate if SUSPENSE)", "Model Invoice Source Row",
    "Model Match Method", "Model TDS Rate % (Inferred)",
    "Model Expected Credit (Hypothesis)", "Model Signed Residual",
    "Model Service / Evidence", "Model SOL ID",
    "Model Proper Client Name",
]
VALID_STATUSES = ("OK", "SUSPENSE", "Duplicate Payment")
BANK_CREDIT_INDEX = 8
STATUS_INDEX = 12
REMARKS_INDEX = 13
MAX_ROWS = 20000


class SuspenseReportBlocked(ValueError):
    pass


def _bank_credit(text):
    """An amount diagnostic, not a payment or matching decision."""
    value = text.strip()
    if not value:
        return "BLANK"
    try:
        money = Decimal(value)
    except InvalidOperation:
        return "INVALID"
    if not money.is_finite():
        return "INVALID"
    return "POSITIVE" if money > 0 else ("ZERO" if money == 0 else "NEGATIVE")


def audit_existing_payment_statuses(rows, *, observed_headers, approved_headers):
    """Group exact existing model status M into read-only report categories.

    Caller must supply independent approved header evidence; matching the
    contract alone does not prove independent approval of underlying rows.
    No statuses are created or recalculated by this function.
    """
    if (approved_headers != PAYMENT_HEADERS
            or observed_headers != approved_headers
            or not isinstance(observed_headers, list)):
        raise SuspenseReportBlocked("APPROVED_PAYMNENT_HEADER_MISMATCH")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise SuspenseReportBlocked("PAYMENT_SNAPSHOT_INVALID")
    groups = {status: [] for status in VALID_STATUSES}
    credits = {status: {"POSITIVE": 0, "ZERO": 0, "BLANK": 0,
                        "NEGATIVE": 0, "INVALID": 0}
               for status in VALID_STATUSES}
    for values in rows:
        if (not isinstance(values, (list, tuple))
                or len(values) != len(PAYMENT_HEADERS)
                or any(not isinstance(cell, str) for cell in values)):
            raise SuspenseReportBlocked("PAYMNENT_SOURCE_VALUES_INCOMPLETE")
        status = values[STATUS_INDEX]
        if status not in groups:
            raise SuspenseReportBlocked("UNAPPROVED_RECONCILIATION_STATUS")
        groups[status].append(tuple(values))
        credits[status][_bank_credit(values[BANK_CREDIT_INDEX])] += 1
    return groups, {
        "result": "REVIEW_ONLY_PRECLASSIFIED_STATUS_REPORT",
        "rows": len(rows),
        "status_counts": {status: len(groups[status]) for status in VALID_STATUSES},
        "credit_diagnostics": credits,
        "classification_source": "EXISTING_PAYMNENT_COLUMN_M_ONLY",
        "original_columns_preserved": "A:L",
        "source_records_modified": 0,
        "source_or_settlement_independently_verified": False,
        "production_release": False,
    }


def suspense_report_csv(rows):
    """Private CSV for existing SUSPENSE rows only, with formula guards."""
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(PAYMENT_HEADERS)
    for row in rows:
        if (not isinstance(row, (tuple, list))
                or len(row) != len(PAYMENT_HEADERS)
                or row[STATUS_INDEX] != "SUSPENSE"):
            raise SuspenseReportBlocked("NOT_A_VERIFIED_SUSPENSE_ROW")
        protected = []
        for value in row:
            if not isinstance(value, str):
                raise SuspenseReportBlocked("SOURCE_CELL_NOT_TEXT")
            if (value.lstrip().startswith(("=", "+", "-", "@"))
                    or value.startswith(("\t", "\r", "\n"))):
                protected.append("'" + value)
            else:
                protected.append(value)
        writer.writerow(protected)
    return out.getvalue().encode("utf-8-sig")
