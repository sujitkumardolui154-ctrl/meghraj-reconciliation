"""Staging-only read adapter for future, certified Credit Note identity indexes.

Never creates, updates or deletes Firestore documents. NOT attached to HTTP
routes. Config and indexes must be independently backfilled/certified first.
Existing invoices referenced by Credit Notes are valid references, NOT new
invoices to import. A read-only preview cannot prevent a write-time race.
"""
import hashlib
import re

from credit_note_validation import (
    INVOICE_ALIASES, CREDIT_NOTE_ALIASES, REPLACEMENT_ALIASES,
    _field, number, audit_credit_note_rows,
)

CONTROL_COLLECTION = "dashboard_cn_registry_control_v1"
CONTROL_DOC = "read_only"
INDEXES = {
    "invoice": ("dashboard_invoice_keys_v140", "invoice_no"),
    "credit_note": ("dashboard_cn_keys_v1", "credit_note_no"),
    "replacement": ("dashboard_cn_replacement_keys_v1", "replacement_invoice_no"),
}
MAX_PREVIEW_ROWS = 20000
SHA = re.compile(r"^[a-f0-9]{64}$")


class RegistryNotCertified(Exception):
    """Safe, non-sensitive code for a blocked preview."""


def _read_certification(db):
    snapshot = db.collection(CONTROL_COLLECTION).document(CONTROL_DOC).get(timeout=30)
    if not snapshot.exists:
        raise RegistryNotCertified("REGISTRY_CONTROL_NOT_FOUND")
    data = snapshot.to_dict()
    if not isinstance(data, dict):
        raise RegistryNotCertified("REGISTRY_CONTROL_INVALID")
    required = (
        data.get("state") == "CERTIFIED_READ_ONLY"
        and data.get("source_verified") is True
        and data.get("backfill_complete") is True
        and data.get("invoice_registry_certified") is True
        and data.get("credit_note_registry_certified") is True
        and data.get("replacement_registry_certified") is True
        and data.get("invoice_key_encoding") == "SHA256_UPPERCASE"
        and data.get("credit_note_key_encoding") == "SHA256_UPPERCASE"
        and data.get("replacement_key_encoding") == "SHA256_UPPERCASE"
        and isinstance(data.get("snapshot_sha256"), str)
        and bool(SHA.fullmatch(data["snapshot_sha256"]))
    )
    if not required:
        raise RegistryNotCertified("REGISTRY_NOT_CERTIFIED")
    return data["snapshot_sha256"]


def _get_all_exact(db, collection, field, values):
    """Return existing canonical identifiers. Missing docs are not invented."""
    found = set()
    keys = sorted({number(value) for value in values if number(value)})
    for start in range(0, len(keys), 200):
        batch = keys[start:start + 200]
        id_to_key = {
            hashlib.sha256(value.encode("utf-8")).hexdigest(): value
            for value in batch
        }
        refs = [
            db.collection(collection).document(doc_id)
            for doc_id in id_to_key
        ]
        snapshots = list(db.get_all(refs, timeout=30))
        if len(snapshots) != len(refs):
            raise RegistryNotCertified("INCOMPLETE_REGISTRY_READ")
        seen = set()
        for snap in snapshots:
            doc_id = getattr(snap, "id", None)
            if doc_id not in id_to_key or doc_id in seen:
                raise RegistryNotCertified("REGISTRY_ID_MISMATCH")
            seen.add(doc_id)
            if not snap.exists:
                continue
            record = snap.to_dict()
            if not isinstance(record, dict) or number(record.get(field)) != id_to_key[doc_id]:
                raise RegistryNotCertified("REGISTRY_VALUE_CONFLICT")
            found.add(id_to_key[doc_id])
        if seen != set(id_to_key):
            raise RegistryNotCertified("INCOMPLETE_REGISTRY_READ")
    return found


def _blocked_preview(rows, reason):
    try:
        audit = audit_credit_note_rows(rows, require_credit_note_numbers=True)
    except (ValueError, TypeError):
        return {
            "rows": [], "summary": {"source_rows": len(rows), "error_rows": 0,
                                    "error_flags": {}, "register_status": "NOT_VERIFIED"},
            "registry_status": "BLOCKED", "reason": "INVALID_CREDIT_NOTE_SOURCE_SCHEMA",
            "import_ready": False, "database_changed": False,
            "financial_writes": 0, "release_status": "REVIEW_REQUIRED",
        }
    for row in audit["rows"]:
        if row["status"] == "SCREENED_REFERENCE_ONLY":
            row["status"] = "REVIEW_PENDING_REGISTRY"
    audit["summary"]["register_status"] = "NOT_VERIFIED"
    return {
        **audit, "registry_status": "BLOCKED", "reason": reason,
        "import_ready": False, "database_changed": False,
        "financial_writes": 0, "release_status": "REVIEW_REQUIRED",
    }


def preview_against_certified_registry(db, rows):
    """Fail closed unless a complete, authorized canonical index is certified.

    This function intentionally does not enable importing even after checks
    succeed. Later writer must use atomic creates and explicit owner approval.
    """
    rows = list(rows)
    if len(rows) > MAX_PREVIEW_ROWS:
        raise ValueError("MAX_20000_ROWS_PER_PREVIEW")
    if not rows:
        raise ValueError("NO_CREDIT_NOTE_ROWS")

    try:
        # Validate the dedicated CN schema before any external reads.
        audit_credit_note_rows(rows, require_credit_note_numbers=True)
        manifest_sha = _read_certification(db)
        invoices = [number(_field(row, INVOICE_ALIASES)) for row in rows]
        cn_numbers = [number(_field(row, CREDIT_NOTE_ALIASES)) for row in rows]
        replacements = [number(_field(row, REPLACEMENT_ALIASES)) for row in rows]
        invoice_found = _get_all_exact(
            db, *INDEXES["invoice"], invoices
        )
        cn_found = _get_all_exact(
            db, *INDEXES["credit_note"], cn_numbers
        )
        replacement_found = _get_all_exact(
            db, *INDEXES["replacement"], replacements
        )
    except RegistryNotCertified as exc:
        return _blocked_preview(rows, str(exc))
    except (ValueError, TypeError):
        return _blocked_preview(rows, "INVALID_CREDIT_NOTE_SOURCE_SCHEMA")
    except Exception:
        # A DB outage, missing permission, or unavailable index must NOT
        # produce a successful uniqueness verification.
        return _blocked_preview(rows, "REGISTRY_READ_UNAVAILABLE")

    audit = audit_credit_note_rows(
        rows,
        existing_credit_note_numbers=cn_found,
        approved_invoice_numbers=invoice_found,
        existing_replacement_invoice_numbers=replacement_found,
        require_credit_note_numbers=True,
    )
    audit["summary"]["register_status"] = "CERTIFIED_READ_ONLY"
    audit["summary"]["registry_snapshot_sha256"] = manifest_sha
    return {
        **audit, "registry_status": "CERTIFIED_READ_ONLY",
        "reason": "FINANCIAL_WRITER_NOT_IMPLEMENTED",
        "import_ready": False, "database_changed": False,
        "financial_writes": 0, "release_status": "REVIEW_REQUIRED",
    }
