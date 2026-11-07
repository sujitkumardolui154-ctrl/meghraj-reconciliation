"""F04 pure read-only evidence boundary. Not wired to live finance or an LLM.

The trusted caller must verify Firebase session revocation and resource ACLs before
supplying records. This module independently enforces UID, tenant, role, provenance,
bounded size and duplicate-reference ambiguity. It never performs I/O.
"""
from decimal import Decimal, InvalidOperation
from typing import Mapping

MAX_RECORDS = 50
MAX_TEXT = 2000
ALLOWED_SOURCES = frozenset({"invoice", "payment", "branch", "reconciliation", "report", "history"})

class EvidenceDenied(ValueError):
    pass

def _required(value, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise EvidenceDenied("Missing or invalid evidence identity")
    return value

def select_evidence(*, principal: Mapping, records, tenant: str, source_version: str):
    """Return minimal evidence; fail closed on incomplete authorization/provenance.

    Records must be independently retrieved and authorized by the upstream
    read-only adapter. No untrusted record can grant itself access.
    """
    uid = _required(principal.get("uid"))
    if principal.get("revoked") is not False or principal.get("authenticated") is not True:
        raise EvidenceDenied("Session not verified")
    if principal.get("tenant") != _required(tenant):
        raise EvidenceDenied("Tenant denied")
    roles = principal.get("roles")
    if not isinstance(roles, (list, tuple, frozenset)) or "sbi_invoice_reader" not in roles:
        raise EvidenceDenied("Role denied")
    version = _required(source_version)
    if not isinstance(records, (list, tuple)) or len(records) > MAX_RECORDS:
        raise EvidenceDenied("Evidence page invalid")
    output = []
    seen = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise EvidenceDenied("Invalid record")
        if record.get("authorized_uid") != uid or record.get("tenant") != tenant:
            raise EvidenceDenied("Resource denied")
        if record.get("source_version") != version:
            raise EvidenceDenied("Stale or conflicting source")
        source = record.get("source")
        if source not in ALLOWED_SOURCES:
            raise EvidenceDenied("Unapproved source")
        row = _required(record.get("row_id"))
        reference = _required(record.get("reference"))
        timestamp = _required(record.get("source_timestamp"))
        citation = f"{source}:{row}@{version}"
        if citation in seen:
            raise EvidenceDenied("Duplicate evidence row")
        seen.add(citation)
        summary = record.get("summary")
        if not isinstance(summary, str) or len(summary) > MAX_TEXT:
            raise EvidenceDenied("Unbounded evidence text")
        output.append({"citation": citation, "reference": reference,
                       "source_timestamp": timestamp, "summary": summary})
    return tuple(output)

def exact_money_sum(values):
    """Deterministic arithmetic for verified inputs, never status allocation."""
    if not isinstance(values, (tuple, list)) or not values or len(values) > MAX_RECORDS:
        raise EvidenceDenied("Invalid money operands")
    total = Decimal("0")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, str):
            raise EvidenceDenied("Money must be source-preserved decimal text")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise EvidenceDenied("Non-numeric money") from exc
        if not amount.is_finite() or amount.as_tuple().exponent < -2:
            raise EvidenceDenied("Unsupported precision")
        total += amount
    return format(total.quantize(Decimal("0.01")), ".2f")
