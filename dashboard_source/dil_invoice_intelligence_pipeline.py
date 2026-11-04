"""F05: evidence-first invoice intelligence orchestration contract.

No network, database, cloud, model, or write capability is implemented here.
The caller must provide independently authenticated identity and a SERVER-SIDE
authorization-checked read-only retrieval adapter. The response composer is
also supplied by the caller and is untrusted until output validation.
This module is preparatory source code; it is NOT a production query engine.
"""
from dataclasses import dataclass
from typing import Callable
import re


MAX_QUERY = 2000
MAX_CONTEXT_TURNS = 8
MAX_EVIDENCE = 25
MAX_ANSWER = 6000
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,159}$")
SOURCE_KINDS = frozenset({
    "invoice", "payment", "branch", "reconciliation", "report", "history"
})


class IntelligenceUnavailable(ValueError):
    """A safe answer cannot currently be supported."""


@dataclass(frozen=True)
class VerifiedCaller:
    uid: str
    permissions: frozenset[str]
    session_revoked: bool = False


@dataclass(frozen=True)
class ChatTurn:
    role: str
    text: str


@dataclass(frozen=True)
class EvidenceRecord:
    kind: str
    record_id: str
    version: str
    observed_at: str
    # Human-readable, redacted evidence summary, not arbitrary external tool text.
    excerpt: str


@dataclass(frozen=True)
class DraftAnswer:
    answer: str
    citations: tuple[str, ...]
    incomplete: bool = False


@dataclass(frozen=True)
class VerifiedAnswer:
    answer: str
    citations: tuple[EvidenceRecord, ...]
    incomplete: bool


# Callback implementations MUST enforce user + row authorization independently;
# the AI composer must never get direct database credentials.
AuthorizedRead = Callable[
    [VerifiedCaller, str, tuple[ChatTurn, ...], int],
    tuple[EvidenceRecord, ...]
]
Compose = Callable[
    [str, tuple[ChatTurn, ...], tuple[EvidenceRecord, ...]],
    DraftAnswer
]


def execute_invoice_question(
    caller: VerifiedCaller,
    question: str,
    context: tuple[ChatTurn, ...],
    authorized_read: AuthorizedRead,
    compose: Compose,
) -> VerifiedAnswer:
    """Accept arbitrary invoice questions; never pretend missing data is verified.

    The actual authorized read adapter, model configuration, output factuality
    checks, rate limits and financial calculation engines remain separate gates.
    """
    if (not isinstance(caller, VerifiedCaller)
            or not isinstance(caller.uid, str) or not caller.uid
            or caller.session_revoked
            or "sbi_invoice_reader" not in caller.permissions):
        raise IntelligenceUnavailable("Invoice access denied")
    if (not isinstance(question, str) or not question.strip()
            or len(question) > MAX_QUERY
            or any(ord(c) < 32 and c not in "\n\t" for c in question)):
        raise IntelligenceUnavailable("Invalid invoice question")
    if not isinstance(context, tuple) or len(context) > MAX_CONTEXT_TURNS:
        raise IntelligenceUnavailable("Conversation context rejected")
    for turn in context:
        if (not isinstance(turn, ChatTurn)
                or turn.role not in {"user", "assistant"}
                or not isinstance(turn.text, str)
                or not turn.text.strip() or len(turn.text) > 1000):
            raise IntelligenceUnavailable("Conversation context rejected")
    if not callable(authorized_read) or not callable(compose):
        raise IntelligenceUnavailable("Invoice intelligence service unavailable")

    # Retrieve through the independently authenticated, server-side read adapter.
    records = authorized_read(caller, question, context, MAX_EVIDENCE)
    if (not isinstance(records, tuple)
            or not 0 < len(records) <= MAX_EVIDENCE):
        raise IntelligenceUnavailable("No verified authorized invoice evidence")

    by_id = {}
    for row in records:
        if (not isinstance(row, EvidenceRecord)
                or row.kind not in SOURCE_KINDS
                or not isinstance(row.record_id, str)
                or not ID_RE.fullmatch(row.record_id)
                or not isinstance(row.version, str)
                or not ID_RE.fullmatch(row.version)
                or not isinstance(row.observed_at, str) or not row.observed_at.strip()
                or not isinstance(row.excerpt, str) or not row.excerpt.strip()
                or len(row.excerpt) > 1500):
            raise IntelligenceUnavailable("Invalid evidence or missing provenance")
        key = row.kind + ":" + row.record_id
        if key in by_id:
            raise IntelligenceUnavailable("Duplicate evidence requires review")
        by_id[key] = row

    draft = compose(question, context, records)
    if (not isinstance(draft, DraftAnswer)
            or not isinstance(draft.answer, str)
            or not draft.answer.strip() or len(draft.answer) > MAX_ANSWER
            or not isinstance(draft.incomplete, bool)
            or not isinstance(draft.citations, tuple)
            or not draft.citations or len(draft.citations) > MAX_EVIDENCE):
        raise IntelligenceUnavailable("Unverified invoice answer")

    ids = set()
    used = []
    for citation in draft.citations:
        if not isinstance(citation, str) or citation not in by_id or citation in ids:
            raise IntelligenceUnavailable("Answer cites unauthorized or duplicate evidence")
        ids.add(citation)
        used.append(by_id[citation])
    return VerifiedAnswer(draft.answer, tuple(used), draft.incomplete)
