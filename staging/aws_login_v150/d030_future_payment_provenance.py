"""D-030: synthetic-only future payment provenance sidecar for existing 3-column UI.

EXPERIMENTAL REVIEW CONTRACT, NOT AN AWS API. Does not open files, connect
to bank/finance data, authenticate real users, read receipts or write records.
It validates fabricated sidecar metadata against a fabricated copy of the
existing Description | SOL ID | Credit Amount upload format. Mock cutoff
dates / source Column-I claims are NOT bank-verified evidence.

All changes to historic invoices, PAYMNENT A-L, allocations, credit notes,
GST and production settlement are prohibited under the owner policy.
"""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

HEADERS = ("Description", "SOL ID", "Credit Amount")
PROVENANCE_KEYS = frozenset((
    "source_kind", "excel_row", "bank_date", "bank_reference",
    "source_credit_column", "source_credit_I",
    "evidence_row_sha256",
))
ROW_RE = re.compile(r"SYNTH-[A-Z0-9][A-Z0-9 _-]{0,190}\Z")
UTR_RE = re.compile(r"SYNTH-UTR-[A-Z0-9_-]{1,80}\Z")
SOL_RE = re.compile(r"[0-9]{1,6}\Z")
MONEY_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")
HEX64_RE = re.compile(r"[a-f0-9]{64}\Z")
ISO_RE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\Z")
MAX_ROWS = 100


class FutureEvidenceBlocked(ValueError):
    pass


def _require(ok, code):
    if not ok:
        raise FutureEvidenceBlocked(code)


def _date(value):
    _require(isinstance(value, str) and ISO_RE.fullmatch(value) is not None,
             "ISO_DATE_REQUIRED")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FutureEvidenceBlocked("INVALID_DATE") from exc


def _money(value):
    _require(isinstance(value, str) and MONEY_RE.fullmatch(value) is not None,
             "MONEY_AS_STRICT_TEXT_REQUIRED")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise FutureEvidenceBlocked("INVALID_MONEY") from exc
    _require(amount.is_finite() and amount > 0 and amount < Decimal("1E13"),
             "POSITIVE_FINITE_CREDIT_REQUIRED")
    return amount


def evidence_row_sha256(row):
    """Deterministic copy-line digest; NOT a bank statement signature."""
    _require(isinstance(row, dict) and set(row) == set(HEADERS),
             "EXACT_EXISTING_3_COLUMN_FORMAT_REQUIRED")
    desc = row["Description"]
    sol = row["SOL ID"]
    _require(isinstance(desc, str) and ROW_RE.fullmatch(desc) is not None,
             "SYNTHETIC_DESCRIPTION_REQUIRED")
    _require(isinstance(sol, str) and SOL_RE.fullmatch(sol) is not None,
             "SOL_TEXT_REQUIRED")
    credit = _money(row["Credit Amount"])
    payload = {
        "schema": "SBI_D030_SYNTHETIC_ROW_V1",
        "description": desc,
        "sol_text": sol,
        "credit": format(credit, ".2f"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _previous_keys(index):
    _require(isinstance(index, (tuple, list)), "MOCK_REFERENCE_INDEX_REQUIRED")
    keys = set()
    for row in index:
        _require(isinstance(row, dict) and set(row) ==
                 {"source_kind", "bank_reference_sha256"} and
                 row["source_kind"] == "SYNTHETIC" and
                 isinstance(row["bank_reference_sha256"], str) and
                 HEX64_RE.fullmatch(row["bank_reference_sha256"]) is not None,
                 "REAL_OR_UNVERIFIED_REFERENCE_INDEX_FORBIDDEN")
        keys.add(row["bank_reference_sha256"])
    return keys


def _reference_hash(ref):
    _require(isinstance(ref, str) and UTR_RE.fullmatch(ref) is not None,
             "SYNTHETIC_BANK_REFERENCE_REQUIRED")
    return hashlib.sha256(
        ("SBI_D030_GLOBAL_BANK_REFERENCE_V1:" + ref).encode()
    ).hexdigest()


def preview_future_evidence(rows, sidecar, *, mock_activation_date,
                            mock_submission_date, synthetic_mode=False,
                            previous_synthetic_references=()):
    """Atomically hold all rows on any mock provenance conflict.

    Standalone pure function. This is NOT proof of actual bank authority,
    real identity, real activation policy or true payment uniqueness. A
    production adapter would need independently authenticated bank evidence
    plus a server-controlled cutoff and transactional unique index.
    """
    _require(synthetic_mode is True, "SYNTHETIC_MODE_REQUIRED")
    activation = _date(mock_activation_date)
    submission = _date(mock_submission_date)
    _require(submission >= activation, "SUBMISSION_BEFORE_CUTOFF")
    _require(isinstance(rows, list) and 0 < len(rows) <= MAX_ROWS,
             "FABRICATED_BATCH_REQUIRED")
    _require(isinstance(sidecar, list) and len(sidecar) == len(rows),
             "ONE_SIDECAR_PER_EVIDENCE_ROW_REQUIRED")
    prior = _previous_keys(previous_synthetic_references)

    reports = []
    ids = []
    row_digests = []
    for index, (source, meta) in enumerate(zip(rows, sidecar), 2):
        holds = []
        refhash = None
        expected = None
        try:
            expected = evidence_row_sha256(source)
        except FutureEvidenceBlocked as exc:
            holds.append(str(exc))
        if not isinstance(meta, dict) or set(meta) != PROVENANCE_KEYS:
            holds.append("PROVENANCE_SCHEMA_MISMATCH")
        elif meta.get("source_kind") != "SYNTHETIC":
            holds.append("REAL_BANK_PROVENANCE_FORBIDDEN")
        else:
            if type(meta["excel_row"]) is not int or meta["excel_row"] != index:
                holds.append("ROW_ORDINAL_MISMATCH")
            declared = meta["evidence_row_sha256"]
            if not isinstance(declared, str) or not HEX64_RE.fullmatch(declared):
                holds.append("EVIDENCE_ROW_DIGEST_INVALID")
            elif expected is not None and declared != expected:
                holds.append("EVIDENCE_ROW_DIGEST_MISMATCH")
            if meta["source_credit_column"] != "PAYMNENT!I":
                holds.append("ORIGINAL_CREDIT_I_LINEAGE_REQUIRED")
            try:
                source_i = _money(meta["source_credit_I"])
                shown_credit = _money(source["Credit Amount"])
                if source_i != shown_credit:
                    holds.append("ORIGINAL_CREDIT_I_MISMATCH")
            except (FutureEvidenceBlocked, KeyError, TypeError):
                holds.append("ORIGINAL_CREDIT_I_INVALID")
            try:
                bank_date = _date(meta["bank_date"])
                if bank_date < activation:
                    holds.append("PRE_ACTIVATION_BANK_DATE_FORBIDDEN")
                if bank_date > submission:
                    holds.append("FUTURE_BANK_DATE_FORBIDDEN")
            except FutureEvidenceBlocked:
                holds.append("BANK_DATE_INVALID")
            try:
                refhash = _reference_hash(meta["bank_reference"])
            except FutureEvidenceBlocked:
                holds.append("BANK_REFERENCE_INVALID")
        ids.append(refhash)
        row_digests.append(expected)
        reports.append({"excel_row": index, "reasons": holds})
    seen = Counter(k for k in ids if k is not None)
    seen_rows = Counter(k for k in row_digests if k is not None)
    for report, refhash, rowhash in zip(reports, ids, row_digests):
        if refhash is not None and seen[refhash] > 1:
            report["reasons"].append("DUPLICATE_BANK_REFERENCE_IN_BATCH")
        if refhash is not None and refhash in prior:
            report["reasons"].append("PRIOR_SYNTHETIC_REFERENCE_CONFLICT")
        if rowhash is not None and seen_rows[rowhash] > 1:
            report["reasons"].append("DUPLICATE_THREE_COLUMN_SOURCE_ROW")
    holds = [{"excel_row": r["excel_row"], "reasons": sorted(set(r["reasons"]))}
             for r in reports if r["reasons"]]
    accepted = [] if holds else [
        {"excel_row": report["excel_row"],
         "bank_reference_sha256": refhash,
         "evidence_row_sha256": digest,
         "status": "SYNTHETIC_ELIGIBILITY_PREVIEW_ONLY"}
        for report, refhash, digest in zip(reports, ids, row_digests)
    ]
    return {
        "schema": "SBI_D030_FUTURE_EVIDENCE_PROVENANCE_V1",
        "mode": "SYNTHETIC_ONLY",
        "status": ("HELD_ATOMICALLY_NO_RECONCILIATION" if holds else
                   "SYNTHETIC_PREVIEW_READY_NO_RECONCILIATION"),
        "source_rows": len(rows),
        "preview_ready_count": len(accepted),
        "held_row_count": len(holds),
        "holds": holds,
        "preview": accepted,
        "source_sheet_original": "NOT_ACCESSED",
        "source_credit_I_claim_verified_against_bank": False,
        "mock_cutoff_is_real_release_cutoff": False,
        "live_payment_uniqueness_certified": False,
        "real_user_authenticated": False,
        "financial_reconciliation_executed": False,
        "historical_data_accessed": False,
        "invoice_or_payment_db_accessed": False,
        "receipt_persisted": False,
        "financial_write_performed": False,
        "production_unlock_allowed": False,
    }
