"""R16 conservative source-to-approved-master *identity shadow*, not financial reconciliation.

No settlement, no SQL/Firestore, no writes, no real user data and no
GitHub-hosted original master. Original workbook and master are explicit
in-memory bytes supplied privately by a future authorized host. All identifiers
remain private; the returned report contains only counts and hashes.

A matching SOL/name does not mean an invoice is paid or a bank credit is linked.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import hmac
import io
import re
import unicodedata
import zipfile

from openpyxl import load_workbook

from sbi_r15_financial_source_preflight import (
    inspect_original_workbook, SourceContractError,
)

MASTER_SHEET = "Clean Branch Master"
INVOICE_SHEET = "Invoice Details."
EXPECTED_INVOICE_HEADERS = {7: "Branch Code", 8: "Client Name", 10: "Invoice No", 13: "SGST"}
# Historical approved source A:AH: J = invoice number, M = SGST. Never relocate money into J/M.
MASTER_REQUIRED_HEADERS = ("Official Branch Name", "SOL ID")
MAX_MASTER_BYTES = 16 * 1024 * 1024
MAX_MASTER_UNPACKED = 64 * 1024 * 1024
MAX_MASTER_ROWS = 25000
MAX_INVOICE_ROWS = 100000
GENERIC_CLIENTS = frozenset({
    "sbi", "state bank of india", "review", "error", "missing",
    "source name unverified", "source data not available",
})


class IdentityGateRefused(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def refuse(code):
    raise IdentityGateRefused(code)


def normalize_name(value):
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).strip().split()).casefold()


def valid_text_sol(cell):
    # Do not convert 123.0 -> "123", drop leading zeroes, or use number formats.
    value = cell.value
    if cell.data_type in ("f", "e") or not isinstance(value, str):
        return ""
    return value if re.fullmatch(r"[0-9]{1,12}", value) else ""


def sha256_verified(data, expected_sha256, invalid_code, mismatch_code):
    if not isinstance(data, bytes) or not data:
        refuse(invalid_code)
    if not isinstance(expected_sha256, str) or not re.fullmatch(
        r"[a-f0-9]{64}", expected_sha256
    ):
        refuse("EXPLICIT_SHA256_MANIFEST_REQUIRED")
    digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(digest, expected_sha256):
        refuse(mismatch_code)
    return digest


def load_master(data):
    if len(data) > MAX_MASTER_BYTES:
        refuse("MASTER_SIZE_LIMIT")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        refuse("MASTER_NOT_XLSX")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(z.file_size for z in archive.infolist()) > MAX_MASTER_UNPACKED:
                refuse("MASTER_UNPACKED_SIZE_LIMIT")
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False,
                             keep_links=False)
    except IdentityGateRefused:
        raise
    except Exception:
        refuse("MASTER_XLSX_UNREADABLE")
    return book


def shadow_identity_preflight(
    source_bytes: bytes,
    master_bytes: bytes,
    *,
    expected_source_sha256: str,
    expected_master_sha256: str,
):
    """Return aggregate *preflight* review counts; never suggest an allocation.

    Hash equality only verifies byte identity to caller-supplied expected hashes.
    It is NOT approval of the master, host fresh-upload provenance, or financial QA.
    """
    source_sha = sha256_verified(
        source_bytes, expected_source_sha256,
        "FRESH_FINANCIAL_SOURCE_BYTES_REQUIRED", "SOURCE_SHA256_MISMATCH",
    )
    master_sha = sha256_verified(
        master_bytes, expected_master_sha256,
        "APPROVED_MASTER_BYTES_REQUIRED", "MASTER_SHA256_MISMATCH",
    )
    try:
        source = inspect_original_workbook(
            source_bytes, expected_sha256=source_sha
        )
    except SourceContractError as err:
        refuse("R15_" + err.code)

    book = load_master(master_bytes)
    try:
        if MASTER_SHEET not in book.sheetnames:
            refuse("MASTER_REQUIRED_SHEET_MISSING")
        sheet = book[MASTER_SHEET]
        if sheet.max_row > MAX_MASTER_ROWS:
            refuse("MASTER_ROW_LIMIT")
        header_to_col = {}
        for idx, cell in enumerate(sheet[1], start=1):
            name = normalize_name(cell.value)
            if name in (normalize_name(s) for s in MASTER_REQUIRED_HEADERS):
                if name in header_to_col:
                    refuse("MASTER_REQUIRED_HEADER_DUPLICATE")
                header_to_col[name] = idx
        if any(normalize_name(key) not in header_to_col
               for key in MASTER_REQUIRED_HEADERS):
            refuse("MASTER_REQUIRED_HEADERS_MISSING")
        name_col = header_to_col[normalize_name("Official Branch Name")]
        sol_col = header_to_col[normalize_name("SOL ID")]
        by_sol = defaultdict(set)
        raw_sol_values = set()
        master_reviews = Counter()
        for row in sheet.iter_rows(min_row=2, max_col=max(name_col, sol_col)):
            name_cell, sol_cell = row[name_col - 1], row[sol_col - 1]
            if name_cell.value is None and sol_cell.value is None:
                continue
            name = normalize_name(name_cell.value)
            sol = valid_text_sol(sol_cell)
            if not sol:
                master_reviews["invalid_or_nontext_sol"] += 1
                continue
            if not name or name in GENERIC_CLIENTS:
                master_reviews["missing_or_generic_official_name"] += 1
                continue
            by_sol[sol].add(name)
            raw_sol_values.add(sol)

        ambiguous = {sol for sol, names in by_sol.items() if len(names) != 1}
        # Numeric-equivalent identifiers are *not* merged: e.g. 00001 != 1.
        padded_keys = defaultdict(set)
        for sol in raw_sol_values:
            padded_keys[sol.lstrip("0") or "0"].add(sol)
        padded_collisions = sum(len(sols) > 1 for sols in padded_keys.values())

        inv = load_workbook(io.BytesIO(source_bytes), read_only=True,
                            data_only=False, keep_links=False)
        try:
            if INVOICE_SHEET not in inv.sheetnames:
                refuse("INVOICE_SHEET_NOT_PRESENT")
            sheet = inv[INVOICE_SHEET]
            if sheet.max_row > MAX_INVOICE_ROWS:
                refuse("INVOICE_ROW_LIMIT")
            for col, label in EXPECTED_INVOICE_HEADERS.items():
                if normalize_name(sheet.cell(1, col).value) != normalize_name(label):
                    refuse("INVOICE_G_H_J_M_HEADER_CONTRACT_MISMATCH")

            invoice_ids = Counter()
            for row in sheet.iter_rows(min_row=2, max_col=19):
                inv_cell = row[9]
                if (inv_cell.data_type not in ("f", "e")
                    and isinstance(inv_cell.value, str)
                    and inv_cell.value.strip()):
                    invoice_ids[inv_cell.value.strip().casefold()] += 1
            duplicated_ids = {key for key, count in invoice_ids.items() if count > 1}
            stats = Counter()
            for row in sheet.iter_rows(min_row=2, max_col=19):
                stats["rows_seen"] += 1
                invoice_cell = row[9]
                value = invoice_cell.value
                invoice_key = (
                    value.strip().casefold()
                    if isinstance(value, str) and invoice_cell.data_type not in ("f", "e")
                    else ""
                )
                if not invoice_key:
                    stats["invoice_no_missing_or_nontext"] += 1
                elif invoice_key in duplicated_ids:
                    stats["duplicate_invoice_rows_quarantined"] += 1
                if row[18].value is not None and not (
                    isinstance(row[18].value, str) and not row[18].value.strip()
                ):
                    stats["protected_paid_marker_s_nonblank"] += 1
                    continue
                stats["s_blank_only"] += 1
                if not invoice_key or invoice_key in duplicated_ids:
                    stats["candidate_identity_on_hold"] += 1
                    continue
                sol = valid_text_sol(row[6])
                if not sol:
                    stats["candidate_missing_or_nontext_sol"] += 1
                    continue
                if sol in ambiguous:
                    stats["candidate_ambiguous_master_sol"] += 1
                    continue
                names = by_sol.get(sol)
                if not names:
                    stats["candidate_sol_not_in_verified_master"] += 1
                    continue
                client = normalize_name(row[7].value)
                if not client or client in GENERIC_CLIENTS or row[7].data_type in ("f", "e"):
                    stats["candidate_unverified_client_name"] += 1
                elif client in names:
                    stats["candidate_exact_sol_and_official_name_only"] += 1
                else:
                    stats["candidate_client_name_mismatch_review"] += 1
        finally:
            inv.close()

        return {
            "stage": "R16_PRIVATE_IDENTITY_SHADOW",
            "source_sha256": source_sha,
            "master_sha256": master_sha,
            "payment_credit_column": source["payment_credit_source"],
            "payment_rows_seen": source["payment_rows_seen"],
            "payment_credit_evidence_counts": source["bank_credit_evidence_counts"],
            "master_official_sol_keys": len(by_sol),
            "master_ambiguous_sol_keys": len(ambiguous),
            "master_padded_sol_collision_groups": padded_collisions,
            "master_invalid_identity_rows": sum(master_reviews.values()),
            "master_invalid_identity_reason_counts": dict(master_reviews),
            "invoice_duplicate_id_groups": len(duplicated_ids),
            "invoice_identity_counts": dict(stats),
            "exact_name_checks_are_not_payment_matches": True,
            "master_aliases_used": False,
            "historical_master_authority_verified": False,
            "source_fresh_upload_attestation_verified": False,
            "v251_allocation_engine_connected": False,
            "financial_database_connected": False,
            "invoice_status_updates": 0,
            "financial_payment_allocations": 0,
            "financial_apply_locked": True,
            "release_authorized": False,
        }
    finally:
        book.close()
