"""D-022 combined SBI source review — read-only, offline, NO settlement.

Integrates actual GitHub invoice-schema, payment-status classifier,
Credit Note report projection, and MXP GST preview contracts.
No caller-supplied 'PASS' booleans can certify live financial parity.
This is NOT a financial allocation engine and never changes protected rows.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "backend_source", ROOT / "staging" / "mxp-gst"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from invoice_source_schema import row_layout, invoice_number, HEADERS_35, HEADERS_53
from payment_report_rules import payment_report_kind
from credit_note_53_adapter import project_credit_notes
from gst_batch_preview import gst_batch_preview


class ReviewInputError(ValueError):
    pass


def _raw_invoice_key(row):
    # Never normalize IDs to digits; preserve exact MXP/source identity.
    try:
        value = invoice_number(row)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ReviewInputError("INVALID_SOURCE_INVOICE_ROW") from exc
    return value if isinstance(value, str) and value == value.strip() else ""


def _validate_invoice(row):
    if not isinstance(row, dict) or row.get("source_sheet") != "Invoice Details.":
        raise ReviewInputError("INVOICE_DETAILS_SHEET_REQUIRED")
    width, *_ = row_layout(row)
    if row.get("original_headers") not in (HEADERS_53, HEADERS_35):
        # Also permit approved 34-column schema through actual row_layout checks;
        # no inferred transformation of source columns or model identity fields.
        from invoice_source_schema import HEADERS_34
        if row.get("original_headers") != HEADERS_34:
            raise ReviewInputError("ORIGINAL_HEADER_CONTRACT_REQUIRED")
    if len(row["original_headers"]) != width:
        raise ReviewInputError("ORIGINAL_HEADER_CONTRACT_REQUIRED")
    key = _raw_invoice_key(row)
    if not key:
        raise ReviewInputError("MISSING_OR_UNTRIMMED_INVOICE_NUMBER")
    return width, key


def _bank_credit_status(row):
    """Read PAYMNENT original A-L, specifically credit in column I (index 8)."""
    if (not isinstance(row, list) or len(row) != 12
            or not all(isinstance(cell, str) for cell in row)):
        raise ReviewInputError("PAYMNENT_ORIGINAL_A_TO_L_REQUIRED")
    raw = row[8].strip()
    if not raw:
        return "NO_CREDIT"
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return "INVALID_CREDIT"
    if not value.is_finite() or value < 0:
        return "INVALID_CREDIT"
    return "VALID_CREDIT" if value > 0 else "ZERO_CREDIT"


def combined_offline_review(invoice_rows, payment_rows, *,
                            gst_sources=None, gst_master=None,
                            original_gst_records=None):
    """Review only private, already-loaded source rows.

    Do not put bank data, invoice values or full results into public logs.
    Source data must be independently authenticated in a future private adapter.
    A lack of original source and ledger parity ALWAYS blocks settlement.
    """
    if not isinstance(invoice_rows, list) or not isinstance(payment_rows, list):
        raise ReviewInputError("BOTH_SOURCE_SHEETS_REQUIRED")
    if not invoice_rows:
        raise ReviewInputError("EMPTY_INVOICE_SOURCE")
    if not payment_rows:
        raise ReviewInputError("EMPTY_PAYMENT_SOURCE")

    # Validate all input before producing any summaries; originals are never edited.
    identities = []
    for row in invoice_rows:
        _, key = _validate_invoice(row)
        identities.append(key)
    counts = Counter(identities)
    statuses = [_bank_credit_status(row) for row in payment_rows]

    payment_counts = Counter(statuses)
    review_counts = Counter()
    credit_note_count = 0
    source_row_flags = []
    for index, (row, key) in enumerate(zip(invoice_rows, identities), 1):
        flags = []
        if counts[key] > 1:
            flags.append("DUPLICATE_INVOICE")
        # Owner-approved Invoice Details. original column S eligibility gate.
        if row["original_values"][18].strip():
            flags.append("COLUMN_S_EXCLUDED")
        if not flags:
            classification = payment_report_kind(row)
            if classification == "error-value":
                flags.append("INVALID_SOURCE_PAYMENT_VALUE")
        # Credit Note module is read-only and strict-schema. For 34-column
        # source the credit-note projection is withheld pending adapter QA.
        if len(row["original_values"]) in (35, 53):
            projected, _ = project_credit_notes(
                row["original_headers"], [row["original_values"]])
            if projected[0]["Credi note"]:
                credit_note_count += 1
                flags.append("CREDIT_NOTE_REVIEW_REQUIRED")
        else:
            flags.append("CREDIT_NOTE_34_COLUMN_ADAPTER_NOT_VERIFIED")
        if not flags:
            flags.append("UNVERIFIED_BANK_ALLOCATION")
        for reason in flags:
            review_counts[reason] += 1
        # Ordinals only; never expose invoice identity/amount in audit summary.
        source_row_flags.append({"source_row_ordinal": index, "flags": flags})

    gst_status = "NOT_REQUESTED"
    gst_count = 0
    gst_review_count = 0
    if any(x is not None for x in (gst_sources, gst_master, original_gst_records)):
        if not all(isinstance(x, list) for x in
                   (gst_sources, gst_master, original_gst_records)):
            raise ReviewInputError("GST_SOURCE_MASTER_ORIGINAL_TRIPLET_REQUIRED")
        gst = gst_batch_preview(gst_sources, gst_master, original_gst_records)
        gst_count = gst["row_count"]
        gst_review_count = gst["review_required"]
        for source in gst_sources:
            if not isinstance(source, dict) or not isinstance(source.get("invoice_no"), str):
                raise ReviewInputError("INVALID_GST_INVOICE_ROW")
            if source["invoice_no"] not in counts:
                review_counts["GST_INVOICE_NOT_IN_SOURCE_LEDGER"] += 1
        # Even READY_FOR_REVIEW GST rows are not source-authenticated/approved.
        gst_status = "PRIVATE_ORIGINAL_PARITY_NOT_VERIFIED"

    return {
        "status": "REVIEW_REQUIRED",
        "source_invoice_rows": len(invoice_rows),
        "source_payment_rows": len(payment_rows),
        "duplicate_source_invoice_groups": sum(n > 1 for n in counts.values()),
        "invoice_review_counts": dict(sorted(review_counts.items())),
        "invoice_row_flags": source_row_flags,
        "bank_credit_classification": {
            name: payment_counts[name]
            for name in ("VALID_CREDIT", "ZERO_CREDIT", "NO_CREDIT", "INVALID_CREDIT")
        },
        "credit_note_tagged_for_review": credit_note_count,
        "gst_rows_previewed": gst_count,
        "gst_rows_requiring_review": gst_review_count,
        "gst_status": gst_status,
        "payment_allocation": "NOT_EXECUTED",
        "source_independent_parity": "NOT_VERIFIED",
        "financial_write_performed": False,
        "approved_for_settlement": False,
        "aws_deployment_performed": False,
    }
