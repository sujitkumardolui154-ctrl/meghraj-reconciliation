"""F06 synthetic composition seam for the DIL evidence-first pipeline.

NO Firestore, API, model, or IAM access. Real-source integration requires a
trusted server-side repository *and* a reviewer-approved per-record permission
policy. Never infer financial record ownership from invoice/SOL labels.
"""
from dataclasses import dataclass
from typing import Callable
try:
    # Normal package import used by synthetic tests.
    from .dil_invoice_intelligence_pipeline import (
        EvidenceRecord, IntelligenceUnavailable, VerifiedCaller, MAX_EVIDENCE,
    )
except ImportError:
    # Production gateway may run from dashboard_source as a script root.
    from dil_invoice_intelligence_pipeline import (
        EvidenceRecord, IntelligenceUnavailable, VerifiedCaller, MAX_EVIDENCE,
    )

ALLOWED = frozenset({"invoice", "payment", "branch", "reconciliation", "report", "history"})


@dataclass(frozen=True)
class CandidateRow:
    kind: str
    record_id: str
    version: str
    observed_at: str
    excerpt: str
    # Scoped metadata is supplied by a trusted server-side repository, not a
    # browser or model prompt. Permission decisions are delegated to policy.
    scope: str


@dataclass(frozen=True)
class TrustedScope:
    """Explicitly validated authorization context from the auth service."""
    uid: str
    scope: str
    verified: bool


ReadCandidates = Callable[[str, int], tuple[CandidateRow, ...]]
CanRead = Callable[[TrustedScope, CandidateRow], bool]


def authorized_invoice_reader(
    caller: VerifiedCaller,
    question: str,
    _context: tuple,
    limit: int,
    *,
    verified_scope: TrustedScope,
    read_candidates: ReadCandidates,
    can_read: CanRead,
) -> tuple[EvidenceRecord, ...]:
    """Fail the entire read if provenance or per-row authorization is unclear.

    The repository must *already* apply verified scope filtering at query time
    so this second per-row check is a defense in depth, not a permission grant.
    A financial record without explicit ownership/branch policy is denied.
    """
    if (
        not isinstance(caller, VerifiedCaller)
        or caller.session_revoked
        or not isinstance(caller.uid, str)
        or not caller.uid.strip()
        or not isinstance(caller.permissions, frozenset)
        or "sbi_invoice_reader" not in caller.permissions
        or not isinstance(verified_scope, TrustedScope)
        or verified_scope.verified is not True
        or not isinstance(verified_scope.uid, str)
        or not verified_scope.uid.strip()
        or verified_scope.uid != caller.uid
        or not isinstance(verified_scope.scope, str)
        or not verified_scope.scope.strip()
        or not isinstance(question, str)
        or not question.strip()
        or not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 0 < limit <= MAX_EVIDENCE
        or not callable(read_candidates)
        or not callable(can_read)
    ):
        raise IntelligenceUnavailable("Verified invoice authorization unavailable")

    # At most limit candidate rows; anything beyond the limit is a hard error,
    # not a partial hidden authorization failure.
    try:
        rows = read_candidates(question, limit)
    except Exception as exc:
        raise IntelligenceUnavailable("Read-only evidence source unavailable") from exc
    if not isinstance(rows, tuple) or len(rows) > limit:
        raise IntelligenceUnavailable("Invalid read-only evidence response")
    result = []
    seen = set()
    for row in rows:
        if (
            not isinstance(row, CandidateRow)
            or not isinstance(row.kind, str)
            or row.kind not in ALLOWED
        ):
            raise IntelligenceUnavailable("Unsupported evidence source")
        if not isinstance(row.scope, str) or not row.scope.strip() or row.scope != verified_scope.scope:
            raise IntelligenceUnavailable("Source scope mismatch")
        # Reject malformed repository evidence before invoking policy callbacks.
        # Policy must never process untrusted or incomplete source metadata.
        if not all(
            isinstance(v, str) and v.strip()
            for v in (row.record_id, row.version, row.observed_at, row.excerpt)
        ):
            raise IntelligenceUnavailable("Missing evidence provenance")
        # A policy adapter must return an explicit boolean. Truthy strings,
        # objects and numeric values are not authorization decisions.
        try:
            decision = can_read(verified_scope, row)
        except Exception as exc:
            raise IntelligenceUnavailable("Per-record permission unavailable") from exc
        if decision is not True:
            raise IntelligenceUnavailable("Per-record permission denied")
        # Validate identifiers before hashing; malformed repository output must
        # raise the controlled unavailable error, never a raw TypeError.
        key = (row.kind, row.record_id)
        if key in seen:
            raise IntelligenceUnavailable("Duplicate evidence requires review")
        seen.add(key)
        result.append(EvidenceRecord(
            row.kind, row.record_id, row.version, row.observed_at, row.excerpt
        ))
    return tuple(result)
