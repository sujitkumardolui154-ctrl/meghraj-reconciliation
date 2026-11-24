"""R25 conservative SOL identity diagnostics, source-only and review-only.

Pure synthetic-testable functions; no workbook import, database access, ledger
matching, API calls, payment allocation or financial status application.
Caller-supplied source identifiers are never rewritten; all candidate SOLs
are explicitly unapproved pending official master/version sign-off.

NOTE: This is NOT a v2.51 payment reconciliation engine.
"""
from __future__ import annotations

from collections import defaultdict
import re
import unicodedata

SOL_PATTERN = re.compile(r"[0-9]{1,12}\Z")
GENERIC_NAMES = frozenset({
    "", "sbi", "state bank of india", "review", "error",
    "missing", "source data not available", "source name unverified",
})


class R25IdentityReviewRefusal(ValueError):
    """Stable fail-closed diagnostic code with no private source values."""


def _norm(value: object) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).strip().casefold().split()
    ) if isinstance(value, str) else ""


def _build_master(master_rows):
    if not isinstance(master_rows, (list, tuple)) or len(master_rows) > 25000:
        raise R25IdentityReviewRefusal("MASTER_ROWS_REQUIRED_LIMITED")
    by_sol: dict[str, set[str]] = defaultdict(set)
    unsafe = []
    for entry in master_rows:
        if not isinstance(entry, (tuple, list)) or len(entry) != 2:
            raise R25IdentityReviewRefusal("MASTER_IDENTITY_PAIR_REQUIRED")
        sol, official = entry
        if not isinstance(sol, str) or not SOL_PATTERN.fullmatch(sol):
            unsafe.append("MASTER_NON_TEXT_OR_MISSING_SOL")
            continue
        name = _norm(official)
        if name in GENERIC_NAMES or not name:
            unsafe.append("MASTER_UNVERIFIED_OFFICIAL_NAME")
            continue
        by_sol[sol].add(name)

    by_unpadded: dict[str, set[str]] = defaultdict(set)
    for sol in by_sol:
        by_unpadded[sol.lstrip("0") or "0"].add(sol)
    return by_sol, by_unpadded, unsafe


def review_identity(source_sol, source_client, master_rows):
    """Return candidates/hold reasons; NEVER a payment match or settlement.

    Numeric source SOL is *not* silently coerced: it may hide lost leading
    zeros. Padded candidates are informational only and preserve source SOL.
    Official names are exact normalized text here; alias approval is external.
    """
    by_sol, by_unpadded, unsafe = _build_master(master_rows)
    candidate = None
    status = "HOLD"
    reasons = []
    normalized_name = _norm(source_client)
    source_sol_is_text = isinstance(source_sol, str)
    if not source_sol_is_text or not SOL_PATTERN.fullmatch(source_sol):
        reasons.append("SOURCE_SOL_NON_TEXT_OR_INVALID_HOLD")
    elif not normalized_name or normalized_name in GENERIC_NAMES:
        reasons.append("SOURCE_CLIENT_UNVERIFIED_HOLD")
    else:
        collisions = by_unpadded.get(source_sol.lstrip("0") or "0", set())
        if source_sol in by_sol:
            if len(by_sol[source_sol]) != 1:
                reasons.append("CONFLICTING_MASTER_OFFICIAL_NAMES_HOLD")
            elif normalized_name in by_sol[source_sol]:
                status = "EXACT_SOL_AND_OFFICIAL_NAME_REVIEW_ONLY"
                candidate = source_sol
            else:
                reasons.append("EXACT_SOL_CLIENT_NAME_MISMATCH_HOLD")
        elif not collisions:
            reasons.append("SOL_NOT_IN_MASTER_HOLD")
        elif len(collisions) > 1:
            reasons.append("AMBIGUOUS_ZERO_PADDED_MASTER_KEYS_HOLD")
        else:
            proposed = next(iter(collisions))
            if len(by_sol[proposed]) != 1:
                reasons.append("CONFLICTING_MASTER_OFFICIAL_NAMES_HOLD")
            elif normalized_name not in by_sol[proposed]:
                reasons.append("PADDED_SOL_NAME_MISMATCH_HOLD")
                candidate = proposed
            else:
                status = "UNIQUE_PADDED_SOL_OFFICIAL_NAME_REVIEW_ONLY"
                candidate = proposed
    if unsafe:
        reasons.append("MASTER_HAS_UNRESOLVED_INVALID_IDENTITIES")
    # A valid exact SOL can coexist with another zero-padded identifier.
    # Never merge '1' with '0001', even if names are coincidentally the same.
    numeric_equivalent_keys = (
        sorted(by_unpadded.get(source_sol.lstrip("0") or "0", ()))
        if isinstance(source_sol, str) and SOL_PATTERN.fullmatch(source_sol)
        else []
    )
    return {
        "stage": "R25_OFFLINE_IDENTITY_REVIEW_ONLY",
        "status": status,
        "source_sol_preserved": source_sol,
        "candidate_master_sol": candidate,
        "numeric_equivalent_master_sols": numeric_equivalent_keys,
        "zero_padding_collision": len(numeric_equivalent_keys) > 1,
        "reason_codes": sorted(set(reasons)),
        "master_invalid_identity_rows": len(unsafe),
        "formal_master_authority_verified": False,
        "approved_alias_equivalence_used": False,
        "financial_status": None,
        "payment_allocation_executed": False,
        "financial_database_connected": False,
        "financial_apply_locked": True,
        "production_release_authorized": False,
    }
