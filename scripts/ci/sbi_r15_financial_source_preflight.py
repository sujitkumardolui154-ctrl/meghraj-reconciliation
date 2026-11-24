"""R15 read-only, synthetic-tested SBI original-workbook integrity preflight.

This is NOT Master v2.51 matching, payment allocation, a financial writer,
a database connector, or permission to use prior Excel reports as fresh input.
Never prints cell content, account data, or transaction values.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import load_workbook

PAYMENT_SHEET = "PAYMNENT"
INVOICE_SHEET = "Invoice Details."
ORIGINAL_PAYMENT_LAST = 12    # A:L preserved, no insertions
ORIGINAL_INVOICE_LAST = 34    # A:AH preserved
CREDIT_COL = 9               # original bank credit I ONLY
PROTECTED_INVOICE_MARKER = 19  # original invoice S; nonblank excludes
MAX_XLSX_BYTES = 30 * 1024 * 1024
MAX_UNPACKED_BYTES = 160 * 1024 * 1024
MAX_SOURCE_ROWS_PER_TAB = 100_000
PAYMENT_HEADER_CONTRACT = {8: "Debit", 9: "Credit", 10: "Balance", 11: "Record For Me"}


class SourceContractError(ValueError):
    """A stable refusal code, with no input values embedded."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _refuse(code: str):
    raise SourceContractError(code)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normal_header(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _classify_credit(cell) -> str:
    # Formula amounts and Excel error cells cannot be accepted as bank evidence.
    value = cell.value
    if _blank(value):
        return "blank"
    if cell.data_type in ("f", "e") or isinstance(value, bool):
        return "review"
    try:
        # Exact Decimal, no float arithmetic; not a proposed TDS/net match.
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "review"
    if not number.is_finite():
        return "review"
    if number < 0:
        return "negative_review"
    if number == 0:
        return "zero"
    return "positive_unallocated"


def inspect_original_workbook(
    raw: bytes, *, expected_sha256: str | None = None
) -> dict:
    """Validate original source shape, returning aggregates only.

    No file writes, calculation of model statuses, allocation, database queries,
    or modification to the supplied workbook bytes.
    """
    if not isinstance(raw, bytes) or not raw:
        _refuse("NEW_XLSX_SOURCE_REQUIRED")
    if len(raw) > MAX_XLSX_BYTES:
        _refuse("SOURCE_SIZE_LIMIT")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        _refuse("SOURCE_SHA256_MISMATCH")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        _refuse("NOT_A_VALID_XLSX_ARCHIVE")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            if sum(item.file_size for item in package.infolist()) > MAX_UNPACKED_BYTES:
                _refuse("SOURCE_UNPACKED_SIZE_LIMIT")
        book = load_workbook(
            io.BytesIO(raw), read_only=True, data_only=False, keep_links=False
        )
    except (OSError, zipfile.BadZipFile, ValueError, KeyError) as exc:
        if isinstance(exc, SourceContractError):
            raise
        _refuse("XLSX_SOURCE_UNREADABLE")

    try:
        required = {PAYMENT_SHEET, INVOICE_SHEET}
        if not required.issubset(set(book.sheetnames)):
            _refuse("WRONG_INPUT_EXACT_SHEET_NAMES_REQUIRED")
        pay = book[PAYMENT_SHEET]
        inv = book[INVOICE_SHEET]
        if pay.max_row > MAX_SOURCE_ROWS_PER_TAB or inv.max_row > MAX_SOURCE_ROWS_PER_TAB:
            _refuse("SOURCE_ROW_LIMIT")
        if inv.max_column < ORIGINAL_INVOICE_LAST:
            _refuse("INVOICE_ORIGINAL_A_TO_AH_MISSING")

        # Protect original H/I/J/K source meanings. L's original header is blank.
        for index, expected in PAYMENT_HEADER_CONTRACT.items():
            if _normal_header(pay.cell(1, index).value) != _normal_header(expected):
                _refuse("PAYMENT_ORIGINAL_H_TO_K_HEADER_MISMATCH")
        if not _blank(pay.cell(1, ORIGINAL_PAYMENT_LAST).value):
            _refuse("PAYMENT_ORIGINAL_L_HEADER_NOT_BLANK")

        credit_counts = dict.fromkeys(
            ("positive_unallocated", "zero", "blank", "negative_review", "review"), 0
        )
        for row in pay.iter_rows(min_row=2, max_col=CREDIT_COL):
            classification = _classify_credit(row[CREDIT_COL - 1])
            credit_counts[classification] += 1

        eligible = protected = 0
        for row in inv.iter_rows(
            min_row=2, min_col=PROTECTED_INVOICE_MARKER,
            max_col=PROTECTED_INVOICE_MARKER
        ):
            if _blank(row[0].value):
                eligible += 1
            else:
                protected += 1

        review = credit_counts["review"] + credit_counts["negative_review"]
        return {
            "stage": "R15_READONLY_SOURCE_PREFLIGHT",
            "source_sha256": digest,
            "source_bytes": len(raw),
            "original_sheet_order_preserved": True,
            "required_original_sheets_present": True,
            "payment_source_columns": "A:L",
            "invoice_source_columns": "A:AH",
            "payment_credit_source": "PAYMNENT!I",
            "excluded_invoice_marker": "Invoice Details.!S",
            "payment_rows_seen": max(0, pay.max_row - 1),
            "invoice_rows_seen": max(0, inv.max_row - 1),
            "bank_credit_evidence_counts": credit_counts,
            "invoice_s_blank_candidate_rows": eligible,
            "invoice_s_nonblank_excluded_rows": protected,
            "source_review_required": bool(review),
            "financial_statuses_written": False,
            "financial_allocation_executed": False,
            "financial_database_connected": False,
            "financial_apply_locked": True,
            "safe_for_automatic_settlement": False,
        }
    finally:
        book.close()
