"""D-002 private source integrity gates. Offline and read-only.

Trusted digests and expected invoice identities must come from a separately
approved, access-controlled manifest. No file/manifest is trusted merely because
the caller supplies it. A successful digest check does not authenticate the
parser or prove per-invoice value parity.
"""
from collections import Counter
import hashlib
import re


class SourceIntegrityError(ValueError):
    pass


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-fA-F0-9]{64}", value) is None:
        raise SourceIntegrityError("UNTRUSTED_OR_INVALID_DIGEST")
    return value.lower()


def verify_file_bytes(file_bytes, approved_sha256):
    """Check actual immutable source bytes against independently approved SHA256."""
    digest = _digest(approved_sha256)
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise SourceIntegrityError("MISSING_SOURCE_BYTES")
    actual = hashlib.sha256(file_bytes).hexdigest()
    if actual != digest:
        raise SourceIntegrityError("SOURCE_SHA256_MISMATCH")
    return {"status": "SOURCE_BYTES_HASH_MATCH", "sha256": actual,
            "financial_write_performed": False, "approved_for_posting": False}


def verify_batch_identity(parsed_records, expected_invoice_numbers):
    """Reject incomplete, duplicated or unexpected invoice identities.

    The approved invoice identity list MUST originate from an independent
    access-controlled manifest, not the same parser being tested.
    """
    if (not isinstance(parsed_records, list)
            or not isinstance(expected_invoice_numbers, (list, tuple))
            or not expected_invoice_numbers):
        raise SourceIntegrityError("APPROVED_BATCH_MANIFEST_REQUIRED")
    def checked_key(value):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise SourceIntegrityError("INVALID_INVOICE_KEY")
        return value
    expected = [checked_key(x) for x in expected_invoice_numbers]
    observed = []
    for rec in parsed_records:
        if not isinstance(rec, dict):
            raise SourceIntegrityError("INVALID_PARSED_RECORD")
        observed.append(checked_key(rec.get("invoice_no")))
    if any(count > 1 for count in Counter(expected).values()):
        raise SourceIntegrityError("DUPLICATE_APPROVED_MANIFEST_INVOICE")
    if any(count > 1 for count in Counter(observed).values()):
        raise SourceIntegrityError("DUPLICATE_ORIGINAL_BATCH_INVOICE")
    if set(expected) != set(observed):
        raise SourceIntegrityError("INCOMPLETE_OR_UNEXPECTED_INVOICE_BATCH")
    return {"status": "BATCH_IDENTITIES_MATCH_MANIFEST",
            "record_count": len(observed), "financial_write_performed": False,
            "approved_for_posting": False}


def verify_private_inputs(source_bytes, approved_source_digest,
                          master_bytes, approved_master_digest,
                          parsed_original_records, approved_invoice_numbers):
    """Combine byte integrity and identity coverage; do not assert value parity."""
    source = verify_file_bytes(source_bytes, approved_source_digest)
    master = verify_file_bytes(master_bytes, approved_master_digest)
    batch = verify_batch_identity(parsed_original_records, approved_invoice_numbers)
    return {
        "status": "INTEGRITY_PRECHECK_PASS",
        "source_sha256": source["sha256"],
        "master_sha256": master["sha256"],
        "batch_record_count": batch["record_count"],
        "original_invoice_values_independently_verified": False,
        "source_parser_provenance_verified": False,
        "financial_write_performed": False,
        "approved_for_posting": False,
    }
