"""DIL free-form invoice question and cited-answer contract (synthetic, no I/O).

This is a deterministic validation layer, NOT an AI model, database gateway,
identity provider, or financial reconciler. Upstream identity / evidence access
must be verified independently before any real deployment.
"""
from dataclasses import dataclass
from typing import Mapping, Sequence
import re


class ChatContractError(ValueError):
    """Request or proposed answer is not safe to present."""


MAX_QUESTION_CHARS = 2000
MAX_CONTEXT_TURNS = 8
MAX_TURN_CHARS = 1000
MAX_ANSWER_CHARS = 6000
MAX_CITATIONS = 25
SOURCE_TYPES = frozenset({
    "invoice", "payment", "branch", "reconciliation", "report", "history"
})
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class Turn:
    role: str
    text: str


@dataclass(frozen=True)
class InvoiceQuestion:
    text: str
    context: tuple[Turn, ...] = ()


@dataclass(frozen=True)
class SourceRef:
    source: str
    record_id: str
    version: str
    observed_at: str


@dataclass(frozen=True)
class CitedAnswer:
    text: str
    citations: tuple[SourceRef, ...]
    incomplete: bool = False


def _safe_text(value: str, max_chars: int) -> bool:
    return (isinstance(value, str) and 0 < len(value.strip()) <= max_chars
            and not any(ord(c) < 32 and c not in "\n\t" for c in value)
            and "\x7f" not in value)


def validate_question(question: InvoiceQuestion) -> InvoiceQuestion:
    """Permit all free-form questions; constrain length and context, not intent.

    No fixed question categories or keyword dispatch: the eventual secure query
    planner must work with the entire natural-language text.
    """
    if not isinstance(question, InvoiceQuestion):
        raise ChatContractError("Invalid question")
    if not _safe_text(question.text, MAX_QUESTION_CHARS):
        raise ChatContractError("Question length or content invalid")
    if not isinstance(question.context, tuple) or len(question.context) > MAX_CONTEXT_TURNS:
        raise ChatContractError("Conversation context limit exceeded")
    for turn in question.context:
        if (not isinstance(turn, Turn)
                or turn.role not in ("user", "assistant")
                or not _safe_text(turn.text, MAX_TURN_CHARS)):
            raise ChatContractError("Invalid conversation context")
    return question


def validate_cited_answer(
    answer: CitedAnswer,
    authorized_evidence: Sequence[SourceRef],
) -> CitedAnswer:
    """Validate provenance against a separately authorized, bounded snapshot.

    Caller MUST first authorize the actual evidence rows for this authenticated
    user. A citation cannot grant itself permission; identifiers are not URLs.
    No direct Firestore/HTTP/model access, no financial writes.
    """
    if not isinstance(answer, CitedAnswer) or not _safe_text(answer.text, MAX_ANSWER_CHARS):
        raise ChatContractError("Invalid response")
    if not isinstance(answer.incomplete, bool):
        raise ChatContractError("Invalid completeness state")
    if not isinstance(answer.citations, tuple) or not answer.citations:
        raise ChatContractError("Answers require authorized evidence citations")
    if len(answer.citations) > MAX_CITATIONS:
        raise ChatContractError("Too many citations")
    if not isinstance(authorized_evidence, (tuple, list)) or len(authorized_evidence) > MAX_CITATIONS:
        raise ChatContractError("Invalid authorized evidence set")

    def key(ref: SourceRef) -> tuple[str, str, str, str]:
        if (not isinstance(ref, SourceRef)
                or ref.source not in SOURCE_TYPES
                or not isinstance(ref.record_id, str)
                or not REF_PATTERN.fullmatch(ref.record_id)
                or not isinstance(ref.version, str)
                or not VERSION_PATTERN.fullmatch(ref.version)
                or not _safe_text(ref.observed_at, 64)):
            raise ChatContractError("Missing or invalid citation provenance")
        return ref.source, ref.record_id, ref.version, ref.observed_at

    allowed = [key(ref) for ref in authorized_evidence]
    if len(set(allowed)) != len(allowed):
        raise ChatContractError("Duplicate authorized source records")
    seen = set()
    for citation in answer.citations:
        identity = key(citation)
        if identity in seen:
            raise ChatContractError("Duplicate citation")
        if identity not in allowed:
            raise ChatContractError("Citation not in authorized evidence")
        seen.add(identity)
    return answer
