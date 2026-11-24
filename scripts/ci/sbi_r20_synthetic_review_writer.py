"""R20 real XLSX serialization for STRICTLY SYNTHETIC REVIEW OUTPUT ONLY.

Not a production financial writer, v2.51/Matrix v2.39 allocation engine, or
financial-status authority. All source IDs, narrations, and master labels must
pass R19's hard synthetic-only fixture gate before serialization. NEVER
accept real SBI workbook bytes. The generated workbook leaves every payment
M status SUSPENSE. Original A:L, A:AH and all other tabs are immutable.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
from decimal import Decimal
import io

from openpyxl import load_workbook

from sbi_r19_combined_synthetic_rehearsal import _strict_synthetic_inputs
from sbi_r16_master_identity_shadow import shadow_identity_preflight
from sbi_r18_output_parity_gate import (
    PAYMENT_MODEL, INVOICE_MODEL, verify_xlsx_output_structure,
)
from sbi_r17_synthetic_financial_shadow import review_one_payment_invoice


class ReviewWriterRefused(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _refuse(code):
    raise ReviewWriterRefused(code)


def create_locked_synthetic_review_xlsx(
    original_bytes: bytes,
    master_bytes: bytes,
    *,
    expected_source_sha256: str,
    expected_master_sha256: str,
):
    """Returns (serialized XLSX bytes, aggregate QA); no disk, SQL or settlement.

    The workbook is for training/staging QA only. Caller must never give it to a
    customer as a reconciled financial workbook.
    """
    if not isinstance(original_bytes, bytes) or not isinstance(master_bytes, bytes):
        _refuse("SYNTHETIC_ORIGINAL_MASTER_BYTES_REQUIRED")
    # First defend by synthetic source-ID AND branch/sol schema, never hashes alone.
    inv, pay = _strict_synthetic_inputs(original_bytes, master_bytes)
    identity = shadow_identity_preflight(
        original_bytes, master_bytes,
        expected_source_sha256=expected_source_sha256,
        expected_master_sha256=expected_master_sha256,
    )
    # This is an identity shadow, not a production master approval.
    if (identity["master_ambiguous_sol_keys"]
            or identity["master_invalid_identity_rows"]
            or identity["invoice_duplicate_id_groups"]):
        _refuse("SYNTHETIC_MASTER_IDENTITY_CONFLICT")
    book = load_workbook(io.BytesIO(original_bytes), data_only=False)
    decisions = Counter()
    try:
        payment_sheet = book["PAYMNENT"]
        invoice_sheet = book["Invoice Details."]

        for i, heading in enumerate(PAYMENT_MODEL, start=13):
            payment_sheet.cell(1, i, heading)
        for i, heading in enumerate(INVOICE_MODEL, start=35):
            invoice_sheet.cell(1, i, heading)

        for row in range(2, payment_sheet.max_row + 1):
            source_id = payment_sheet.cell(row, 4).value
            source = pay.get(source_id)
            if source is None:
                _refuse("SYNTHETIC_PAYMENT_ROW_MISSING")
            refs = source.narration_refs
            if len(refs) == 1 and refs[0] in inv:
                review = review_one_payment_invoice(source, inv[refs[0]])
                decision = review["decision"]
                if decision == "CANDIDATE_FOR_INDEPENDENT_REVIEW":
                    decision = "UNVERIFIED_MATH_REVIEW"
            elif not refs:
                decision = "NO_EXACT_MXP_REFERENCE"
            else:
                decision = "CONTRADICTORY_REFERENCE_OR_UNAVAILABLE_INVOICE"
            if Decimal(source.credit) <= 0:
                decision = "NONPOSITIVE_CREDIT_REVIEW"
            decisions[decision] += 1

            payment_sheet.cell(row, 13, "SUSPENSE")
            payment_sheet.cell(row, 14, "SYNTHETIC QA HOLD; NO FINANCIAL AUTHORIZATION")
            payment_sheet.cell(row, 17, "R20_SYNTHETIC_WRITER_REVIEW_ONLY")
            payment_sheet.cell(row, 21, decision)
            # V/W represent typed observed synthetic identity, NOT approved SBI SOL.
            payment_sheet.cell(row, 22, source.sol)
            payment_sheet.cell(row, 23, source.client)

        for row in range(2, invoice_sheet.max_row + 1):
            invoice_id = invoice_sheet.cell(row, 13).value
            invoice = inv.get(invoice_id)
            if invoice is None:
                _refuse("SYNTHETIC_INVOICE_ROW_MISSING")
            if invoice.original_s_marker is not None and invoice.original_s_marker != "":
                invoice_sheet.cell(row, 39, "SYNTHETIC S NONBLANK — EXCLUDED")
                continue
            invoice_sheet.cell(row, 35, invoice.sol)
            invoice_sheet.cell(row, 36, invoice.client)
            invoice_sheet.cell(row, 39, "SYNTHETIC NOT LINKED TO BANK")
        stream = io.BytesIO()
        book.save(stream)
        out = stream.getvalue()
    finally:
        book.close()

    structural = verify_xlsx_output_structure(
        original_bytes, out,
        expected_source_sha256=expected_source_sha256,
        expected_candidate_sha256=sha256(out).hexdigest(),
    )
    if structural["payment_status_counts_structure_only"].get("OK", 0):
        _refuse("UNAUTHORIZED_FINANCIAL_OK")
    if structural["payment_status_counts_structure_only"].get("Duplicate Payment", 0):
        _refuse("UNAUTHORIZED_DUPLICATE_STATUS")
    if (structural["payment_status_counts_structure_only"].get("SUSPENSE", 0)
            != sum(1 for item in pay.values() if item.credit and Decimal(item.credit) > 0)):
        _refuse("POSITIVE_SOURCE_PAYMENT_STATUS_COVERAGE_MISSING")

    return out, {
        "stage": "R20_SYNTHETIC_REVIEW_XLSX_SERIALIZER",
        "source_sha256": expected_source_sha256,
        "master_sha256": expected_master_sha256,
        "output_sha256": sha256(out).hexdigest(),
        "model_columns": ["M:W", "AI:AM"],
        "original_source_preserved": True,
        "review_classification_counts": dict(decisions),
        "all_payment_statuses_locked_suspense": True,
        "financial_apply_locked": True,
        "v251_certified": False,
        "real_v218_writer_verified": False,
        "financial_database_connected": False,
    }
