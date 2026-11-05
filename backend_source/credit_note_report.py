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


# Ordered ORIGINAL 53-column positions, not name lookups. Original headers
# contain duplicate "Client Name" and "Branch Code" labels: source A and
# K must not overwrite approved source H and G respectively.
SOURCE_POSITIONS_53 = (
    1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
)


def generate_credit_note_report_from_53(source_rows, *, approved_53_headers):
    """Project original 53-cell rows into the 18-column report without mutation.

    approved_53_headers must be independently provided by the caller. This
    function checks exact positions against the repository's existing
    import schema; it does NOT certify the approver or the source snapshot.
    The final 18th column is the derived CREDIT NOTE label only.
    """
    from invoice_source_schema import HEADERS_53

    if (not isinstance(approved_53_headers, list)
            or len(approved_53_headers) != 53
            or approved_53_headers != HEADERS_53):
        raise ValueError("Approved 53-column header proof missing or mismatched")
    if len(SOURCE_POSITIONS_53) != len(SOURCE_HEADERS) or len(set(SOURCE_HEADERS)) != 17:
        raise ValueError("CREDIT NOTE source positional projection invalid")
    if not isinstance(source_rows, list):
        raise ValueError("53-column source rows must be a list")
    projected = []
    for source in source_rows:
        if not isinstance(source, dict):
            raise ValueError("53-column source record must be a dictionary")
        values = source.get("original_values")
        if (not isinstance(values, list) or len(values) != 53
                or any(not isinstance(value, str) for value in values)):
            raise ValueError("Original 53-column values are missing or incomplete")
        if ("original_headers" in source
                and source["original_headers"] != approved_53_headers):
            raise ValueError("Source row header positions mismatch approved headers")
        projected.append({
            header: values[index]
            for header, index in zip(SOURCE_HEADERS, SOURCE_POSITIONS_53)
        })
    report, summary = generate_credit_note_report(projected)
    summary["source_projection"] = "ORIGINAL_53_POSITIONAL"
    summary["exact_header_match_to_caller_reference"] = True
    summary["independent_source_approval"] = False
    return report, summary


def generate_credit_note_report_from_source_layout(source_rows, *, approved_headers):
    """Read-only 34/35/53 source adapter for the approved 18-column report.

    The caller must provide the exact approved ordered source headers. This
    adapter does not certify that approval or authorize financial release.
    """
    from invoice_source_schema import (
        HEADERS_34, HEADERS_35, HEADERS_53, export_values_53,
    )

    if not isinstance(approved_headers, list):
        raise ValueError("Approved source header proof is missing")
    if approved_headers not in (HEADERS_34, HEADERS_35, HEADERS_53):
        raise ValueError("Unrecognized source header order")
    if not isinstance(source_rows, list):
        raise ValueError("Source rows must be a list")
    converted = []
    for row in source_rows:
        if not isinstance(row, dict) or row.get("original_headers") != approved_headers:
            raise ValueError("Source row header proof mismatch")
        converted.append({
            "original_headers": HEADERS_53,
            "original_values": export_values_53(row),
        })
    result, summary = generate_credit_note_report_from_53(
        converted, approved_53_headers=HEADERS_53
    )
    summary["source_projection"] = f"ORIGINAL_{len(approved_headers)}_POSITIONAL"
    summary["independent_source_approval"] = False
    return result, summary
