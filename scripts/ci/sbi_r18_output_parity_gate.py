"""R18 source certification gate and v2.18 Excel structural parity validator.

Does not reconcile, issue statuses, write Excel outputs, connect to bank/DB
or certify a Master v2.51 engine. This is a synthetic-only CI aid.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
from itertools import zip_longest
import io
import re
from typing import Mapping
from openpyxl import load_workbook

from sbi_r15_financial_source_preflight import (
    inspect_original_workbook, SourceContractError, _classify_credit,
)

PAYMENT = "PAYMNENT"
INVOICES = "Invoice Details."
PAYMENT_MODEL = (
    "Model Reconciliation Status",
    "Model Reconciliation Remarks",
    "Model Invoice No (Candidate if SUSPENSE)",
    "Model Invoice Source Row",
    "Model Match Method",
    "Model TDS Rate % (Inferred)",
    "Model Expected Credit (Hypothesis)",
    "Model Signed Residual",
    "Model Service / Evidence",
    "Model SOL ID",
    "Model Proper Client Name",
)
INVOICE_MODEL = (
    "Model SOL ID", "Model Proper Client Name", "Model Linked Bank Row (Working)",
    "Model Linked Bank Credit", "Model Match Evidence",
)
ALLOWED_STATUSES = frozenset(("OK", "SUSPENSE", "Duplicate Payment"))
REJECTED_RECOVERED_SOURCE_HASHES = frozenset((
    "72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf",
    "6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3",
))
MAX_BYTES = 30 * 1024 * 1024


class R18GateError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def refuse(code):
    raise R18GateError(code)


def digest(data: bytes, expected: str | None, type_name: str) -> str:
    if not isinstance(data, bytes) or not data:
        refuse(f"{type_name}_BYTES_REQUIRED")
    if len(data) > MAX_BYTES:
        refuse(f"{type_name}_TOO_LARGE")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        refuse(f"{type_name}_EXPECTED_SHA256_REQUIRED")
    actual = sha256(data).hexdigest()
    if actual != expected:
        refuse(f"{type_name}_SHA256_MISMATCH")
    return actual


def audit_candidate_source(candidate_bytes: bytes | None, source_manifest: Mapping | None) -> dict:
    """A digest and claimed version cannot substitute for independent QA signoff."""
    if candidate_bytes is None or source_manifest is None:
        return {
            "stage": "R18_V251_SOURCE_ATTESTATION_GATE",
            "gate": "BLOCKED_CANDIDATE_SOURCE_OR_MANIFEST_MISSING",
            "master_v251_certified": False,
            "matrix_v239_certified": False,
            "financial_apply_locked": True,
        }
    if not isinstance(source_manifest, Mapping):
        refuse("CANDIDATE_MANIFEST_INVALID")
    expected = source_manifest.get("expected_sha256")
    if expected in REJECTED_RECOVERED_SOURCE_HASHES:
        refuse("OLDER_RECOVERED_REVIEW_SOURCE_DENIED")
    source_sha = digest(candidate_bytes, expected, "ENGINE_SOURCE")
    if source_sha in REJECTED_RECOVERED_SOURCE_HASHES:
        refuse("OLDER_RECOVERED_REVIEW_SOURCE_DENIED")
    if (source_manifest.get("claimed_master_version") != "v2.51"
            or source_manifest.get("claimed_matrix_version") != "v2.39"):
        refuse("CANDIDATE_VERSION_NOT_V251_V239")
    return {
        "stage": "R18_V251_SOURCE_ATTESTATION_GATE",
        "gate": "HASHED_CANDIDATE_AWAITING_INDEPENDENT_QUALIFICATION",
        "candidate_source_sha256": source_sha,
        "candidate_signature_verified": False,
        "approved_rulebook_implementation_verified": False,
        "full_method_coverage_verified": False,
        "master_v251_certified": False,
        "matrix_v239_certified": False,
        "real_bank_parity_verified": False,
        "financial_apply_locked": True,
    }


def _cell_identity(cell):
    return (cell.value, cell.data_type, cell.number_format)


def _compare_original_region(source, candidate, max_col: int):
    if source.max_row != candidate.max_row:
        refuse("SOURCE_ROW_COUNT_CHANGED")
    for row_s, row_c in zip_longest(
        source.iter_rows(min_row=1, max_row=source.max_row, max_col=max_col),
        candidate.iter_rows(min_row=1, max_row=candidate.max_row, max_col=max_col),
    ):
        if row_s is None or row_c is None:
            refuse("SOURCE_ROW_COUNT_CHANGED")
        if any(_cell_identity(s) != _cell_identity(c) for s, c in zip(row_s, row_c)):
            refuse("PROTECTED_ORIGINAL_VALUE_FORMULA_FORMAT_CHANGED")


def verify_xlsx_output_structure(
    source_bytes: bytes,
    candidate_bytes: bytes,
    *,
    expected_source_sha256: str,
    expected_candidate_sha256: str,
) -> dict:
    """Validate Excel structure only; this method cannot validate finance values."""
    source_sha = digest(source_bytes, expected_source_sha256, "SOURCE")
    candidate_sha = digest(candidate_bytes, expected_candidate_sha256, "CANDIDATE")
    try:
        preflight = inspect_original_workbook(source_bytes, expected_sha256=source_sha)
    except SourceContractError as e:
        refuse("R15_" + e.code)
    original = None
    written = None
    try:
        original = load_workbook(io.BytesIO(source_bytes), read_only=True,
                                 data_only=False, keep_links=False)
        written = load_workbook(io.BytesIO(candidate_bytes), read_only=True,
                                data_only=False, keep_links=False)
        if original.sheetnames != written.sheetnames:
            refuse("SHEET_NAMES_ORDER_OR_COUNT_CHANGED")
        p_source, i_source = original[PAYMENT], original[INVOICES]
        p_out, i_out = written[PAYMENT], written[INVOICES]
        if p_source.max_column > 12 or i_source.max_column > 34:
            refuse("SOURCE_ALREADY_HAS_MODEL_COLUMNS")
        if p_out.max_column != 23 or i_out.max_column != 39:
            refuse("WRONG_V218_MODEL_COLUMN_BOUNDARIES")

        for j, name in enumerate(PAYMENT_MODEL, start=13):
            if p_out.cell(1, j).value != name:
                refuse("PAYMENT_M_TO_W_HEADER_MISMATCH")
        for j, name in enumerate(INVOICE_MODEL, start=35):
            if i_out.cell(1, j).value != name:
                refuse("INVOICE_AI_TO_AM_HEADER_MISMATCH")

        _compare_original_region(p_source, p_out, 12)
        _compare_original_region(i_source, i_out, 34)
        other_tabs = 0
        for name in original.sheetnames:
            if name in (PAYMENT, INVOICES):
                continue
            s, c = original[name], written[name]
            if s.max_column != c.max_column:
                refuse("ORIGINAL_OTHER_SHEET_COLUMN_BOUNDARY_CHANGED")
            _compare_original_region(s, c, s.max_column)
            other_tabs += 1

        status_counts = Counter()
        for row in p_out.iter_rows(min_row=2, max_col=13):
            credit_class = _classify_credit(row[8])
            status = row[12].value
            if status is not None and status not in ALLOWED_STATUSES:
                refuse("PAYMENT_MODEL_M_INVALID_STATUS")
            if credit_class == "positive_unallocated" and status is None:
                refuse("POSITIVE_PAYMENT_ROW_M_BLANK")
            if credit_class in ("zero", "blank", "negative_review", "review") and status in ("OK", "Duplicate Payment"):
                refuse("NONPOSITIVE_OR_UNVERIFIED_CREDIT_NOT_SETTLEABLE")
            if credit_class == "positive_unallocated" and status is not None:
                status_counts[status] += 1

        return {
            "stage": "R18_V218_XLSX_STRUCTURE_ONLY",
            "source_sha256": source_sha,
            "candidate_sha256": candidate_sha,
            "source_original_payment_columns": "A:L",
            "source_original_invoice_columns": "A:AH",
            "model_payment_columns": "M:W",
            "model_invoice_columns": "AI:AM",
            "other_original_tabs_preserved": other_tabs,
            "original_payment_rows": preflight["payment_rows_seen"],
            "original_invoice_rows": preflight["invoice_rows_seen"],
            "payment_status_counts_structure_only": dict(status_counts),
            "original_cells_formulas_number_formats_preserved": True,
            "model_financial_statuses_certified": False,
            "model_money_parity_certified": False,
            "full_v251_engine_connected": False,
            "financial_database_connected": False,
            "financial_apply_locked": True,
        }
    except R18GateError:
        raise
    except Exception:
        refuse("OUTPUT_XLSX_UNREADABLE")
    finally:
        if original is not None:
            original.close()
        if written is not None:
            written.close()
