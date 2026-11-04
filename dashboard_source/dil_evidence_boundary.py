"""F02 synthetic-only authorization and evidence boundary; no database or model I/O.

All caller identities and rows must originate from independently verified services.
This module does NOT establish authentication or grant report access.
"""
from dataclasses import dataclass
from typing import Mapping, Sequence


class EvidenceDenied(ValueError):
    """A requested source cannot be safely used as answer evidence."""


@dataclass(frozen=True)
class Principal:
    uid: str
    tenant: str
    roles: frozenset[str]
    revoked: bool = False


@dataclass(frozen=True)
class Evidence:
    source: str
    record_id: str
    tenant: str
    owner_uid: str
    required_role: str
    version: str
    observed_at: str
    fields: Mapping[str, str]


ALLOWED_SOURCES = frozenset({
    "invoice", "payment", "branch", "reconciliation", "report", "history"
})
MAX_EVIDENCE = 25


def authorize_evidence(principal: Principal, records: Sequence[Evidence]) -> tuple[Evidence, ...]:
    """Fail the whole request closed rather than silently mixing authorized rows."""
    if not isinstance(principal, Principal) or principal.revoked:
        raise EvidenceDenied("Identity unavailable or revoked")
    if not principal.uid or not principal.tenant or not principal.roles:
        raise EvidenceDenied("Incomplete identity")
    if len(records) > MAX_EVIDENCE:
        raise EvidenceDenied("Evidence limit exceeded")
    result = []
    seen = set()
    for record in records:
        if not isinstance(record, Evidence):
            raise EvidenceDenied("Invalid evidence")
        if (record.source not in ALLOWED_SOURCES
                or record.tenant != principal.tenant
                or record.owner_uid != principal.uid
                or not record.required_role
                or record.required_role not in principal.roles
                or not record.record_id or not record.version
                or not record.observed_at):
            raise EvidenceDenied("Evidence authorization or provenance failed")
        key = (record.source, record.record_id)
        if key in seen:
            raise EvidenceDenied("Duplicate evidence identifier requires review")
        seen.add(key)
        result.append(record)
    return tuple(result)
