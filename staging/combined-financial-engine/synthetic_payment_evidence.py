"""D-027 synthetic-only Payment Evidence Intake PREVIEW contract.

This module is an in-memory prototype, not a deployed upload API. It reads no
workbooks/files, calls no database/network, creates no persistent receipt,
and performs no financial allocations. It deliberately rejects any historical
payment, including synthetic payment dates before a supplied activation date.

An authenticated server adapter and protected append-only receipt store do NOT
exist in this module; the caller's mock actor/date are test fixtures, not auth.
"""
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

_ALLOWED_KEYS = frozenset((
    "source_kind", "payment_id", "original_A_to_L",
    "payment_date", "sol_id", "sbisa", "utr",
    "narration", "invoice_ref", "proof_name", "proof_sha256",
))
_MONEY = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_MOCK_ID = re.compile(r"SYNTH-(?:PAY|UTR|INV|USER)-[A-Z0-9_-]{1,64}\Z")


class EvidenceIntakeBlocked(ValueError):
    pass


def _require(ok, reason):
    if not ok:
        raise EvidenceIntakeBlocked(reason)


def _iso_date(raw):
    _require(isinstance(raw, str) and
             re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", raw) is not None,
             "ISO_DATE_REQUIRED")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise EvidenceIntakeBlocked("INVALID_DATE") from exc


def _mock_id(raw, category):
    _require(isinstance(raw, str) and _MOCK_ID.fullmatch(raw) is not None
             and raw.startswith("SYNTH-" + category + "-"),
             "SYNTHETIC_" + category + "_REQUIRED")
    return raw


def _validated(row, activation, submitted):
    _require(isinstance(row, dict) and row.get("source_kind") == "SYNTHETIC",
             "REAL_OR_HISTORICAL_SOURCE_FORBIDDEN")
    _require(set(row) == _ALLOWED_KEYS, "EVIDENCE_SCHEMA_MISMATCH")
    key = _mock_id(row["payment_id"], "PAY")
    original = row["original_A_to_L"]
    _require(isinstance(original, list) and len(original) == 12
             and all(isinstance(v, str) and len(v) <= 512 for v in original),
             "ORIGINAL_A_TO_L_REQUIRED")
    # Original column I is the ONLY source credit amount, never metadata.
    raw_credit = original[8]
    _require(_MONEY.fullmatch(raw_credit) is not None,
             "ORIGINAL_COLUMN_I_CREDIT_INVALID")
    try:
        credit = Decimal(raw_credit)
    except InvalidOperation as exc:
        raise EvidenceIntakeBlocked("ORIGINAL_COLUMN_I_CREDIT_INVALID") from exc
    _require(credit.is_finite() and credit > 0,
             "ORIGINAL_COLUMN_I_CREDIT_NOT_POSITIVE")
    paid = _iso_date(row["payment_date"])
    _require(paid >= activation, "PRE_ACTIVATION_PAYMENT_FORBIDDEN")
    _require(paid <= submitted, "FUTURE_BANK_CREDIT_FORBIDDEN")
    _require(type(row["sbisa"]) is bool, "SBISA_MARKER_REQUIRED")
    sol = row["sol_id"]
    _require(isinstance(sol, str) and re.fullmatch(r"[0-9]{1,5}", sol)
             or sol == "" and row["sbisa"], "SOL_REQUIRED")
    sol = (sol or "1").zfill(5)
    _require(not row["sbisa"] or sol == "00001", "SBISA_REQUIRES_SOL_1")
    utr = _mock_id(row["utr"], "UTR")
    narration = row["narration"]
    _require(isinstance(narration, str) and 0 < len(narration.strip()) <= 512,
             "BANK_NARRATION_REQUIRED")
    ref = row["invoice_ref"]
    _require(ref is None or isinstance(ref, str) and _MOCK_ID.fullmatch(ref)
             and ref.startswith("SYNTH-INV-"),
             "SYNTHETIC_INVOICE_REFERENCE_REQUIRED")
    proof_name = row["proof_name"]
    proof_hash = row["proof_sha256"]
    _require((proof_name is None and proof_hash is None) or
             (isinstance(proof_name, str)
              and re.fullmatch(r"SYNTH-[A-Za-z0-9_.-]{1,90}\.(?:pdf|xlsx|csv)", proof_name)
              and isinstance(proof_hash, str)
              and _HEX64.fullmatch(proof_hash) is not None),
             "PROOF_METADATA_INVALID")
    # Binary evidence is NOT read. Proof sha256 is caller-supplied metadata only.
    stable = json.dumps({
        "a_l": original, "payment_date": paid.isoformat(),
        "sol": sol, "utr": utr, "sbisa": row["sbisa"],
        "narration": narration, "invoice_ref": ref,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(stable).hexdigest()
    utr_key = hashlib.sha256((sol + ":" + utr).encode()).hexdigest()
    return {"payment_id": key, "fingerprint": fingerprint,
            "utr_key": utr_key, "credit": str(credit)}


def preview_synthetic_new_evidence(rows, *, activation_date, submitted_date,
                                   actor_id, mock_role,
                                   existing_synthetic_receipts=(),
                                   synthetic_mode=False):
    """Simulate preview, duplicate checks, receipts; no durable saves or matches.

    Date/role inputs are explicitly simulated and MUST NOT be trusted for
    production. Real activation time must be server controlled in a future
    authenticated intake service, and duplicate checking transactional.
    """
    _require(synthetic_mode is True, "SYNTHETIC_ONLY")
    _require(mock_role == "SYNTHETIC_PAYMENT_EVIDENCE_UPLOADER",
             "MOCK_UPLOAD_ROLE_REQUIRED")
    _mock_id(actor_id, "USER")
    activation, submitted = _iso_date(activation_date), _iso_date(submitted_date)
    _require(submitted >= activation, "SUBMISSION_BEFORE_ACTIVATION_FORBIDDEN")
    _require(isinstance(rows, list) and 0 < len(rows) <= 100,
             "NEW_EVIDENCE_BATCH_REQUIRED")
    _require(isinstance(existing_synthetic_receipts, (list, tuple)),
             "SYNTHETIC_RECEIPT_INDEX_REQUIRED")

    known_fingerprints = set()
    known_utr_keys = set()
    for receipt in existing_synthetic_receipts:
        _require(isinstance(receipt, dict)
                 and receipt.get("source_kind") == "SYNTHETIC"
                 and isinstance(receipt.get("receipt_id"), str)
                 and re.fullmatch(r"SYNTH-RCPT-[0-9A-F]{20}", receipt["receipt_id"])
                 and isinstance(receipt.get("fingerprint"), str)
                 and _HEX64.fullmatch(receipt["fingerprint"])
                 and isinstance(receipt.get("utr_key"), str)
                 and _HEX64.fullmatch(receipt["utr_key"]),
                 "HISTORICAL_OR_UNVERIFIED_RECEIPTS_FORBIDDEN")
        known_fingerprints.add(receipt["fingerprint"])
        known_utr_keys.add(receipt["utr_key"])

    valid = []
    reasons = {}
    for index, row in enumerate(rows, 1):
        try:
            valid.append((index, _validated(row, activation, submitted)))
        except EvidenceIntakeBlocked as exc:
            # Do not echo private fields or put source values into logs.
            reasons[index] = str(exc)
    fingerprint_counts = Counter(x["fingerprint"] for _, x in valid)
    utr_counts = Counter(x["utr_key"] for _, x in valid)
    payment_counts = Counter(x["payment_id"] for _, x in valid)
    preview = []
    receipts = []
    for index, data in valid:
        if payment_counts[data["payment_id"]] != 1:
            reasons[index] = "DUPLICATE_PAYMENT_ID"
        elif utr_counts[data["utr_key"]] != 1:
            reasons[index] = "DUPLICATE_OR_CONFLICTING_UTR_IN_BATCH"
        elif fingerprint_counts[data["fingerprint"]] != 1:
            reasons[index] = "DUPLICATE_SOURCE_ROW_IN_BATCH"
        elif data["fingerprint"] in known_fingerprints:
            reasons[index] = "ALREADY_PREVIEWED_EVIDENCE"
        elif data["utr_key"] in known_utr_keys:
            reasons[index] = "EXISTING_UTR_CONFLICT"
        else:
            receipt_id = ("SYNTH-RCPT-" + data["fingerprint"][:20].upper())
            receipts.append({
                "source_kind": "SYNTHETIC",
                "receipt_id": receipt_id,
                "fingerprint": data["fingerprint"],
                "utr_key": data["utr_key"],
                "status": "PREVIEW_ONLY_NOT_STORED",
            })
            preview.append({"source_row_ordinal": index,
                            "receipt_id": receipt_id,
                            "status": "PREVIEW_READY_NOT_IMPORTED"})
    holds = [{"source_row_ordinal": i, "reason": reasons[i]}
             for i in sorted(reasons)]
    return {
        "status": "SYNTHETIC_PREVIEW_ONLY",
        "input_rows": len(rows),
        "preview_ready_count": len(preview),
        "held_count": len(holds),
        "preview_receipts": receipts,
        "preview_rows": preview,
        "holds": holds,
        "persistent_receipts_created": False,
        "payment_file_uploaded": False,
        "bank_amounts_processed_for_matching": False,
        "historical_records_accessed": False,
        "historical_recalculation": False,
        "live_financial_writes": False,
        "approved_for_import": False,
        "production_deployed": False,
    }
