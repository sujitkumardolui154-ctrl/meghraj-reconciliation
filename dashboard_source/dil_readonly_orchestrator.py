"""F43 synthetic-only read-only evidence retrieval orchestration.

No HTTP route, database connection, LLM, or financial status mutation.
The adapter is a trusted server-constructed object, NEVER client-provided.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

MAX_RESULTS = 20
MAX_QUERY = 2000
MAX_CONTEXT = 8
SAFE_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,119}$")
AMOUNT = re.compile(r"^-?(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,2})?$")


class RetrievalDenied(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    uid: str
    role: str
    session_verified: bool
    revoked: bool = False


def retrieve(question, *, principal, adapter, context=()):
    """Return only independently authorized evidence; never infer a financial status.

    Adapter contract: search_readonly(query, uid, role, limit) -> iterable of
    mappings with source_id, source_version, authorized_uid, allowed_roles,
    authorized, snippet, and optionally amount. Adapter must enforce ACL
    in its storage layer; this boundary re-checks all returned records.
    """
    if (not isinstance(principal, Principal) or not principal.session_verified
            or principal.revoked or not principal.uid or principal.role not in
            {"invoice_viewer", "supervisor", "admin"}):
        raise RetrievalDenied("AUTH_REQUIRED")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUERY:
        raise RetrievalDenied("INVALID_QUERY")
    if not isinstance(context, (list, tuple)) or len(context) > MAX_CONTEXT:
        raise RetrievalDenied("INVALID_CONTEXT")
    for turn in context:
        if not isinstance(turn, str) or len(turn) > MAX_QUERY:
            raise RetrievalDenied("INVALID_CONTEXT")
    if not callable(getattr(adapter, "search_readonly", None)):
        raise RetrievalDenied("TRUSTED_ADAPTER_REQUIRED")
    # Context is informational, never a grant of authority or a database selector.
    results = adapter.search_readonly(query=question.strip(), uid=principal.uid,
                                      role=principal.role, limit=MAX_RESULTS)
    if not isinstance(results, (list, tuple)) or len(results) > MAX_RESULTS:
        raise RetrievalDenied("RESULT_LIMIT")
    if not results:
        return {"answer": "No verified authorized evidence was found.",
                "evidence": [], "status": "NOT_VERIFIABLE"}
    evidence, seen = [], set()
    for item in results:
        if not isinstance(item, dict):
            raise RetrievalDenied("INVALID_EVIDENCE")
        source_id, version = item.get("source_id"), item.get("source_version")
        if (not isinstance(source_id, str) or not SAFE_SOURCE.fullmatch(source_id)
                or not isinstance(version, str) or not SAFE_SOURCE.fullmatch(version)
                or (source_id, version) in seen):
            raise RetrievalDenied("INVALID_OR_DUPLICATE_SOURCE")
        if (item.get("authorized") is not True
                or item.get("authorized_uid") != principal.uid
                or not isinstance(item.get("allowed_roles"), (tuple, list))
                or principal.role not in item["allowed_roles"]):
            raise RetrievalDenied("EVIDENCE_ACCESS_DENIED")
        snippet = item.get("snippet")
        if not isinstance(snippet, str) or len(snippet) > 1000:
            raise RetrievalDenied("INVALID_SNIPPET")
        entry = {"source_id": source_id, "source_version": version, "snippet": snippet}
        if "amount" in item:
            raw = item["amount"]
            if not isinstance(raw, str) or not AMOUNT.fullmatch(raw):
                raise RetrievalDenied("INVALID_AMOUNT")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise RetrievalDenied("INVALID_AMOUNT") from exc
            if not value.is_finite():
                raise RetrievalDenied("INVALID_AMOUNT")
            entry["amount"] = raw
        seen.add((source_id, version))
        evidence.append(entry)
    # Explicitly return evidence only. No generative synthesis or automatic OK.
    return {"answer": "Verified source excerpts are available for review.",
            "evidence": evidence, "status": "EVIDENCE_ONLY"}
