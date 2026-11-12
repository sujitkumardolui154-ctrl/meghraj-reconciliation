"""Offline, read-only preflight for historical SBI invoice/CN identity indexes.

This is evidence generation, NOT index backfill or certificate creation.
It never reads a live database, writes a financial record or grants approval.
The caller must supply independently verified, complete original records.
"""
import hashlib
from collections import Counter
from collections.abc import Mapping
from credit_note_validation import (
    INVOICE_ALIASES, CREDIT_NOTE_ALIASES, REPLACEMENT_ALIASES,
    _field, number, valid_mxp_reference,
)

MAX_AUDIT_ROWS = 500000


def _summarize(rows, aliases):
    if rows is None:
        return {
            "source_provided": False,
            "rows": 0, "valid_number_rows": 0,
            "missing_number_rows": 0, "invalid_non_mxp_rows": 0,
            "duplicate_groups": 0, "duplicate_affected_rows": 0,
            "unique_valid_numbers": 0,
            "candidate_key_sha256": None,
        }
    counts = Counter()
    missing = 0
    invalid = 0
    total = 0
    for row in rows:
        total += 1
        if total > MAX_AUDIT_ROWS:
            raise ValueError("AUDIT_SOURCE_OVER_MAX_ROWS")
        if not isinstance(row, Mapping):
            raise ValueError("AUDIT_SOURCE_ROW_NOT_MAPPING")
        key = number(_field(row, aliases))
        if not key or key in {"NA", "N/A"}:
            missing += 1
        elif not valid_mxp_reference(key):
            invalid += 1
        else:
            counts[key] += 1
    hashes = sorted(hashlib.sha256(key.encode("utf-8")).hexdigest() for key in counts)
    h = hashlib.sha256()
    for digest in hashes:
        h.update(digest.encode("ascii") + b"\n")
    return {
        "source_provided": True,
        "rows": total,
        "valid_number_rows": sum(counts.values()),
        "missing_number_rows": missing,
        "invalid_non_mxp_rows": invalid,
        "duplicate_groups": sum(value > 1 for value in counts.values()),
        "duplicate_affected_rows": sum(value for value in counts.values() if value > 1),
        "unique_valid_numbers": len(counts),
        "candidate_key_sha256": h.hexdigest(),
    }


def audit_historical_registry_sources(invoice_rows=None, credit_note_rows=None,
                                      replacement_rows=None, *, source_proofs=None):
    """Assess candidate identity datasets; return blockers, never certification.

    Full, independently certified input provenance, unresolved duplicates,
    the existing invoice-key canonicalization, and real index completeness
    require separate evidence before any database control can be certified.
    """
    groups = {
        "invoices": _summarize(invoice_rows, INVOICE_ALIASES),
        "credit_notes": _summarize(credit_note_rows, CREDIT_NOTE_ALIASES),
        "replacement_invoices": _summarize(replacement_rows, REPLACEMENT_ALIASES),
    }
    blockers = []
    for label, summary in groups.items():
        if not summary["source_provided"]:
            blockers.append(label + ":MISSING_VERIFIED_SOURCE")
        elif (
            summary["missing_number_rows"]
            or summary["invalid_non_mxp_rows"]
            or summary["duplicate_groups"]
        ):
            blockers.append(label + ":INVALID_OR_DUPLICATE_IDENTITIES")
    # A self-declared proof is not independent authorization.
    if not isinstance(source_proofs, Mapping) or not all(
        isinstance(source_proofs.get(key), str)
        and len(source_proofs[key]) == 64
        and all(ch in "0123456789abcdef" for ch in source_proofs[key])
        for key in ("invoice_sha256", "credit_note_sha256", "replacement_sha256")
    ):
        blockers.append("ORIGINAL_SOURCE_HASH_EVIDENCE_MISSING")
    blockers.extend([
        "INDEPENDENT_SOURCE_AUTHENTICATION_NOT_VERIFIED",
        "EXISTING_KEY_INDEX_PARITY_NOT_VERIFIED",
        "CREDIT_NOTE_INDEX_BACKFILL_NOT_VERIFIED",
        "OWNER_REVIEW_AND_ATOMIC_WRITE_GATES_NOT_GRANTED",
    ])
    return {
        "groups": groups,
        "blockers": sorted(set(blockers)),
        "candidate_keys_only": True,
        "index_backfill_performed": False,
        "certificate_created": False,
        "can_certify": False,
        "production_import_enabled": False,
        "release_status": "REVIEW_REQUIRED",
        "financial_writes": 0,
    }
