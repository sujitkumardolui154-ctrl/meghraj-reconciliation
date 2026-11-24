"""Read-only payment evidence bridge. No financial settlement or writer access.

Invoked only after Firebase session/CSRF, receipt ownership, original parser,
SHA-256 and summary verification in reconciliation_readiness.py. No raw bank
amount, customer, description or SOL value is returned by this module.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import os
import re

OWNER_UPLOAD_CUTOFF_IST = "2026-11-23T00:00:00+05:30"
HEADERS = ("Description", "SOL ID", "Credit Amount")
MAX_XLSX_BYTES = 8 * 1024 * 1024
MAX_REVIEW_ROWS = 10_000
QUARANTINE_ENV = "SBI_READONLY_QUARANTINE_SOL_KEYS"


class ReviewBridgeBlocked(ValueError):
    """Safe machine-readable hold; never echo private financial cells."""


def require(ok, reason):
    if not ok:
        raise ReviewBridgeBlocked(reason)


def quarantine_keys_from_env():
    raw = os.environ.get(QUARANTINE_ENV, "")
    if not raw:
        return None
    pieces = raw.split(",")
    require(0 < len(pieces) <= 2000, "QUARANTINE_CONFIG_INVALID")
    values = set()
    for item in pieces:
        key = item.strip()
        require(re.fullmatch(r"[1-9][0-9]{0,11}", key) is not None,
                "QUARANTINE_CONFIG_INVALID")
        require(key not in values, "QUARANTINE_CONFIG_DUPLICATE")
        values.add(key)
    return values


def cutoff_evidence(created):
    require(isinstance(created, str) and len(created) <= 45,
            "RECEIPT_DATE_REQUIRED")
    try:
        instant = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewBridgeBlocked("RECEIPT_DATE_INVALID") from exc
    require(instant.tzinfo is not None and instant.utcoffset() is not None,
            "RECEIPT_DATE_TIMEZONE_REQUIRED")
    is_new = instant >= datetime.fromisoformat(OWNER_UPLOAD_CUTOFF_IST)
    return {
        "owner_confirmed_intake_cutoff_ist": OWNER_UPLOAD_CUTOFF_IST,
        "receipt_after_cutoff": is_new,
        "read_only_intake_scope": (
            "NEW_UPLOAD_REVIEW" if is_new else "PRE_CUTOFF_UPLOAD_PROTECTED"
        ),
        "bank_transaction_date_known": False,
        "bank_payment_proven_new": False,
    }


def review_verified_receipt(source, *, expected_sha256, receipt_created_utc,
                            original_parsed, quarantine_keys=None):
    """Return redacted review flags without creating a bank transaction."""
    require(type(source) is bytes and 0 < len(source) <= MAX_XLSX_BYTES,
            "SOURCE_SIZE_INVALID")
    require(type(expected_sha256) is str and
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "EXPECTED_HASH_INVALID")
    require(sha256(source).hexdigest() == expected_sha256,
            "SOURCE_HASH_CHANGED")
    require(type(original_parsed) is dict and
            original_parsed.get("header") == list(HEADERS) and
            original_parsed.get("review_rows") == 0,
            "ORIGINAL_PARSE_NOT_CLEAR")
    cutoff = cutoff_evidence(receipt_created_utc)
    if quarantine_keys is None:
        quarantine_keys = quarantine_keys_from_env()
    if quarantine_keys is not None:
        require(type(quarantine_keys) is set and
                all(type(k) is str and
                    re.fullmatch(r"[1-9][0-9]{0,11}", k)
                    for k in quarantine_keys), "QUARANTINE_CONFIG_INVALID")
    from openpyxl import load_workbook
    try:
        book = load_workbook(BytesIO(source), read_only=True, data_only=False,
                             keep_links=False)
    except Exception as exc:
        raise ReviewBridgeBlocked("STORED_XLSX_INVALID") from exc
    records = []
    similarities = Counter()
    try:
        sheet = (book["PAYMENT EVIDENCE"] if "PAYMENT EVIDENCE" in book
                 else book.active)
        head = [sheet.cell(1, c).value for c in range(1, 5)]
        require(tuple(head[:3]) == HEADERS and head[3] in (None, ""),
                "EXCEL_HEADER_CHANGED")
        for row_index, cells in enumerate(
                sheet.iter_rows(min_row=2, max_col=4), start=2):
            if all(c.value in (None, "") for c in cells):
                continue
            require(len(records) < MAX_REVIEW_ROWS, "FULL_REVIEW_LIMIT_10000")
            require(cells[3].value in (None, "") and
                    all(c.data_type != "f" for c in cells[:3]),
                    "EXTRA_COLUMN_OR_FORMULA_REVIEW")
            desc, sol, raw_amount = (c.value for c in cells[:3])
            require(type(desc) is str and bool(desc.strip()) and
                    len(desc) <= 1000, "DESCRIPTION_INVALID")
            require(type(sol) is str and
                    re.fullmatch(r"[0-9]{1,12}", sol) is not None and
                    bool(sol.strip("0")), "SOL_TEXT_INVALID")
            require(type(raw_amount) in (str, int, float, Decimal),
                    "CREDIT_TYPE_INVALID")
            number = str(raw_amount).replace(",", "").strip()
            if number.startswith("₹"):
                number = number[1:].strip()
            try:
                credit = Decimal(number)
            except InvalidOperation as exc:
                raise ReviewBridgeBlocked("CREDIT_INVALID") from exc
            require(credit.is_finite() and credit > 0 and
                    credit.as_tuple().exponent >= -2, "CREDIT_PAISE_INVALID")
            normalized = json.dumps(
                [desc.strip().casefold(), sol.lstrip("0"),
                 format(credit, ".2f")],
                ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            fingerprint = sha256(normalized).hexdigest()
            similarities[fingerprint] += 1
            records.append((row_index, sol.lstrip("0"), fingerprint))
    finally:
        book.close()
    require(bool(records), "NO_PAYMENT_ROWS")
    require(original_parsed.get("source_rows") == len(records) and
            original_parsed.get("valid_rows") == len(records),
            "EXCEL_SOURCE_ROW_COUNT_CHANGED")
    counts = Counter()
    redacted = []
    for row_index, key, fingerprint in records:
        flags = ["BANK_ORIGIN_DATE_UTR_MISSING", "PRODUCTION_APPLY_LOCKED",
                 "COMPLETE_RULEBOOK_AUTHORITY_UNVERIFIED"]
        if quarantine_keys is None:
            flags.append("PRIVATE_MASTER_QUARANTINE_CONFIG_UNAVAILABLE")
        elif key in quarantine_keys:
            flags.append("BLOCKED_SOL_IDENTITY_GROUP")
        if similarities[fingerprint] > 1:
            flags.append("SAME_LOOKING_UPLOAD_ROWS_NOT_BANK_DUPLICATE_PROOF")
        counts.update(flags)
        if len(redacted) < 25:
            redacted.append({"source_row": row_index, "review_holds": flags})
    return {
        "adapter": "R4_STAGED_RECEIPT_READ_ONLY_REVIEW",
        "receipt_source_sha256": expected_sha256,
        "evidence_rows_reviewed": len(records),
        "all_rows_reviewed": True,
        "owner_confirmed_upload_cutoff": cutoff,
        "financial_status_assigned": False,
        "bank_origin_authenticated": False,
        "payment_identity_utr_verified": False,
        "master_financial_authority_verified": False,
        "quarantine_configuration_present": quarantine_keys is not None,
        "review_hold_counts": dict(sorted(counts.items())),
        "row_review_redacted": redacted,
        "row_review_limit": 25,
        "bank_transaction_date_verified": False,
        "provisional_matrix_only": True,
        "financial_apply_locked": True,
        "financial_writes": False,
        "report_writer_invoked": False,
        "financial_invoice_matches": 0,
        "settlements_created": 0,
    }
