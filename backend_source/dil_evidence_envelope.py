"""F43 source-only evidence-envelope validator; no database/network/model access.

A caller MUST independently authenticate the session, authorize every source row and
verify source-version freshness before passing an envelope. Validation is not RBAC.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

class EvidenceRejected(ValueError):
    pass

_ALLOWED = frozenset({"invoice", "payment", "sol", "reconciliation", "report", "history"})
_MAX_ITEMS = 25
_MAX_TEXT = 4000

def validate_answer(envelope: Mapping, *, authorized_refs: frozenset[str]) -> dict:
    """Return a bounded display-safe copy, or reject the entire ungrounded answer."""
    if not isinstance(envelope, Mapping) or not isinstance(authorized_refs, frozenset):
        raise EvidenceRejected("INVALID_ENVELOPE")
    if set(envelope) != {"answer", "evidence", "status"}:
        raise EvidenceRejected("INVALID_FIELDS")
    answer, evidence, status = envelope["answer"], envelope["evidence"], envelope["status"]
    if not isinstance(answer, str) or not answer.strip() or len(answer) > _MAX_TEXT:
        raise EvidenceRejected("INVALID_ANSWER")
    if not isinstance(status, str) or status not in ("GROUNDED", "INSUFFICIENT_EVIDENCE"):
        raise EvidenceRejected("INVALID_STATUS")
    if not isinstance(evidence, list) or len(evidence) > _MAX_ITEMS:
        raise EvidenceRejected("INVALID_EVIDENCE")
    if status == "GROUNDED" and not evidence:
        raise EvidenceRejected("MISSING_EVIDENCE")
    safe = []
    seen = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"source", "ref", "version", "observed_at"}:
            raise EvidenceRejected("INVALID_SOURCE")
        source, ref, version, observed = (item[k] for k in ("source", "ref", "version", "observed_at"))
        if not isinstance(source, str) or source not in _ALLOWED or not isinstance(ref, str) or not ref or len(ref) > 160:
            raise EvidenceRejected("INVALID_REFERENCE")
        if ref not in authorized_refs:
            raise EvidenceRejected("UNAUTHORIZED_REFERENCE")
        if not isinstance(version, str) or not version.strip() or len(version) > 128:
            raise EvidenceRejected("UNVERSIONED_SOURCE")
        if not isinstance(observed, str) or len(observed) < 20 or len(observed) > 40:
            raise EvidenceRejected("MISSING_TIMESTAMP")
        try:
            timestamp = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceRejected("INVALID_TIMESTAMP") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise EvidenceRejected("UNZONED_TIMESTAMP")
        if timestamp.astimezone(timezone.utc) > datetime.now(timezone.utc):
            raise EvidenceRejected("FUTURE_TIMESTAMP")
        if (source, ref) in seen:
            raise EvidenceRejected("DUPLICATE_REFERENCE")
        seen.add((source, ref))
        safe.append(dict(item))
    return {"answer": answer, "status": status, "evidence": safe}

def exact_money(value: str) -> Decimal:
    """Parse finite decimal strings without float coercion or implicit rounding."""
    if not isinstance(value, str) or not value or len(value) > 40:
        raise EvidenceRejected("INVALID_AMOUNT")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise EvidenceRejected("INVALID_AMOUNT") from exc
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise EvidenceRejected("INVALID_AMOUNT")
    return amount
