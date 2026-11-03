"""Read-only CREDIT NOTE report builder (source values retained verbatim)."""

import re
from collections import Counter


HEADERS = [
    "FY",
    "Invoice Branch",
    "Invoice Generate Location",
    "Month",
    "Invoice Date",
    "Branch Code",
    "Client Name",
    "GST NO",
    "Invoice No",
    "Taxable Amount",
    "CGST",
    "SGST",
    "Total Bill Amount",
    "Less TDS",
    "Actual Reciaveable Ammount Deductionof TDS (Including GST)",
    "Taxable Amount Less TDS (Without GST)",
    "Payment Received (If With GST or Excluding GST)",
    "Credi note",
]

SOURCE_HEADERS = HEADERS[:-1]
PAYMENT_FIELD = SOURCE_HEADERS[-1]

# Approved user rule: CREDIT NOTE or common CREDIT NORTE typing variant as
# independent tokens anywhere in original payment narration (Column U).
# A full token boundary prevents CREDIT NOTEBOOK false positives.
CREDIT_NOTE_PATTERN = re.compile(r"(?<!\w)CREDIT\s+NO(?:TE|RTE)(?!\w)", re.IGNORECASE)


def generate_credit_note_report(source_rows):
    """Preserve original values and identify explicit CREDIT NOTE records."""
    result = []
    all_invoices = set()
    credit_note_invoices = set()
    missing_invoice_numbers = 0
    missing_credit_note_invoice_numbers = 0
    records_by_invoice = {}

    for source in source_rows:
        if not isinstance(source, dict):
            raise ValueError("Source record must be a dictionary")

        missing = [h for h in SOURCE_HEADERS if h not in source]
        if missing:
            raise ValueError("Missing source headers: " + ", ".join(missing))

        invoice = str(source["Invoice No"] or "").strip()

        if invoice:
            all_invoices.add(invoice)
        else:
            missing_invoice_numbers += 1

        narration = str(source[PAYMENT_FIELD] or "")
        is_credit_note = bool(CREDIT_NOTE_PATTERN.search(narration))

        row = {h: source[h] for h in SOURCE_HEADERS}
        row["Credi note"] = (
            "CREDIT NOTE" if is_credit_note else ""
        )

        if is_credit_note:
            if invoice:
                credit_note_invoices.add(invoice)
            else:
                missing_credit_note_invoice_numbers += 1
        if invoice:
            records_by_invoice.setdefault(invoice, []).append((
                is_credit_note, tuple(str(source[h]) for h in SOURCE_HEADERS)
            ))
        result.append(row)

    conflicting = [
        invoice for invoice, items in records_by_invoice.items()
        if len(items) > 1 and any(matched for matched, _ in items)
        and (len({matched for matched, _ in items}) > 1
             or len({values for _, values in items}) > 1)
    ]
    duplicate_groups = sum(len(items) > 1 for items in records_by_invoice.values())
    summary = {
        "total_source_rows": len(result),
        "unique_invoices": len(all_invoices),
        "credit_note_invoices": len(credit_note_invoices),
        "credit_note_unambiguous_invoices": len(credit_note_invoices) - len(conflicting),
        "credit_note_conflict_groups": len(conflicting),
        "duplicate_invoice_groups": duplicate_groups,
        "missing_credit_note_invoice_numbers": missing_credit_note_invoice_numbers,
        "release_status": "REVIEW_REQUIRED",
        "independent_source_approval": False,
        "missing_invoice_numbers": missing_invoice_numbers,
        "source_records_modified": 0,
    }

    return result, summary
