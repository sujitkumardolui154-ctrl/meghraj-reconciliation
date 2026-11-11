"""F02 evidence boundary: synthetic, read-only, deny-by-default retrieval.

No database adapter, model provider or production route is wired here.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Sequence

MAX_QUERY_CHARS = 2000
MAX_RESULTS = 25
ALLOWED_SOURCES = frozenset({"invoice", "payment", "branch", "reconciliation", "report", "history"})


class AccessDenied(Exception):
    """Caller or requested evidence is not authorized."""


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    roles: frozenset[str]
    active: bool


@dataclass(frozen=True)
class Evidence:
    source: str
    record_id: str
    tenant_id: str
    allowed_roles: frozenset[str]
    version: str
    fields: Mapping[str, str]


def retrieve(
    principal: Principal,
    question: str,
    source: str,
    fetch: Callable[[str, str, int], Sequence[Evidence]],
    *,
    limit: int = 10,
) -> tuple[Evidence, ...]:
    """Fetch candidates with tenant scope, then independently authorize each record.

    The fetch adapter must enforce tenant scoping at the datastore boundary too.
    No records are returned if the adapter violates its tenant isolation contract.
    """
    if not principal.active or not principal.user_id or not principal.tenant_id or not principal.roles:
        raise AccessDenied("inactive or incomplete identity")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUERY_CHARS:
        raise ValueError("invalid query length")
    if source not in ALLOWED_SOURCES or type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise ValueError("invalid source or result limit")
    records = fetch(principal.tenant_id, question, limit)
    if len(records) > limit:
        raise AccessDenied("adapter exceeded result limit")
    verified = []
    for record in records:
        if not isinstance(record, Evidence) or record.source != source:
            raise AccessDenied("invalid evidence source")
        if record.tenant_id != principal.tenant_id or not principal.roles.intersection(record.allowed_roles):
            raise AccessDenied("evidence scope denied")
        if not record.record_id or not record.version:
            raise AccessDenied("missing evidence provenance")
        verified.append(record)
    return tuple(verified)


def decimal_total(values: Sequence[str]) -> Decimal:
    """Deterministic arithmetic only; does not infer payment status."""
    total = Decimal("0")
    for value in values:
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("non-numeric financial evidence") from None
        if not amount.is_finite():
            raise ValueError("non-finite financial evidence")
        total += amount
    return total


def cite(record: Evidence) -> str:
    if not record.record_id or not record.version:
        raise AccessDenied("uncitable evidence")
    return f"{record.source}:{record.record_id}@{record.version}"
