"""F43 offline, fail-closed evidence boundary. No database client or network access.

The caller must authenticate independently, supply a verified immutable scope,
and implement a trusted read-only source adapter. Never accept model-generated
scope, source rows or authorizations as proof of access.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping, Sequence

MAX_QUESTION = 2000
MAX_ROWS = 50
MAX_EVIDENCE = 20


class EvidenceDenied(PermissionError):
    pass


@dataclass(frozen=True)
class VerifiedScope:
    subject: str
    tenant: str
    permitted_sol: frozenset[str]
    session_verified: bool
    revoked: bool = False


@dataclass(frozen=True)
class Evidence:
    source: str
    source_hash: str
    row: int
    invoice_no: str
    sol: str
    fields: Mapping[str, str]

    @property
    def citation(self) -> str:
        return f"{self.source}@{self.source_hash}:row-{self.row}"


def money(value: str) -> Decimal:
    """Strict monetary conversion; never round or silently replace malformed values."""
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid monetary evidence") from exc
    if not result.is_finite():
        raise ValueError("nonfinite monetary evidence")
    return result


def authorized_evidence(
    question: str,
    scope: VerifiedScope,
    fetch: Callable[[str, int], Sequence[Evidence]],
    *,
    limit: int = MAX_ROWS,
) -> tuple[Evidence, ...]:
    """Retrieve bounded records, rechecking every row against verified server scope.

    fetch is a trusted server-side read-only adapter; its result is still untrusted
    until checked. No query generation, finance writes or model calls occur here.
    """
    if not isinstance(scope, VerifiedScope) or not scope.session_verified or scope.revoked:
        raise EvidenceDenied("verified active session required")
    if not scope.subject or not scope.tenant or not scope.permitted_sol:
        raise EvidenceDenied("verified tenant and SOL scope required")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise ValueError("invalid question")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_ROWS:
        raise ValueError("invalid row limit")
    rows = fetch(question, limit)
    if not isinstance(rows, (list, tuple)) or len(rows) > limit:
        raise EvidenceDenied("source exceeded bounded result contract")
    accepted = []
    for row in rows:
        if not isinstance(row, Evidence) or row.sol not in scope.permitted_sol:
            raise EvidenceDenied("source returned unauthorized row")
        if not row.source or not row.source_hash or len(row.source_hash) != 64 or any(
            c not in "0123456789abcdef" for c in row.source_hash
        ) or not isinstance(row.row, int) or row.row < 1:
            raise EvidenceDenied("source provenance not verified")
        if not isinstance(row.fields, Mapping) or len(row.fields) > 35:
            raise EvidenceDenied("source field contract invalid")
        accepted.append(row)
    return tuple(accepted[:MAX_EVIDENCE])


def evidence_answer(rows: Sequence[Evidence]) -> dict:
    """No LLM-generated financial assertion: only evidence citations and uncertainty."""
    if not rows:
        return {"status": "NOT_VERIFIABLE", "citations": [], "message": "No authorized supporting evidence."}
    return {
        "status": "EVIDENCE_ONLY",
        "citations": [row.citation for row in rows],
        "message": "Authorized source records retrieved; independent interpretation required.",
    }
