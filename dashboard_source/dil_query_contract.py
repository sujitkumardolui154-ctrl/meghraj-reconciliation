"""F43 read-only DIL request and evidence boundary; no database or model access.

This pure module deliberately does not accept an identity from client JSON.
The HTTP integration must supply a revocation-verified session user and
server-side entitlement, then authorize each retrieved record separately.
"""
import re
from decimal import Decimal, InvalidOperation, localcontext

MAX_QUESTION = 2000
MAX_CONTEXT = 8
MAX_EVIDENCE = 20
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,119}$")


class QueryDenied(ValueError):
    pass


def validate_query(payload, *, session_user, session_identity):
    """Fail closed before any retrieval, model call, or financial calculation."""
    if not isinstance(session_identity, dict) or session_user is None:
        raise QueryDenied("AUTH_REQUIRED")
    uid = session_identity.get("uid")
    if not isinstance(uid, str) or not uid or getattr(session_user, "uid", None) != uid:
        raise QueryDenied("SESSION_IDENTITY_MISMATCH")
    if getattr(session_user, "disabled", True):
        raise QueryDenied("ACCOUNT_DISABLED")
    claims = getattr(session_user, "custom_claims", None)
    if not isinstance(claims, dict) or claims.get("dil_dashboard") is not True:
        raise QueryDenied("DASHBOARD_ACCESS_DENIED")
    if claims.get("sbi_invoice_chat_viewer") is not True:
        raise QueryDenied("INVOICE_CHAT_ACCESS_DENIED")
    if not isinstance(payload, dict) or set(payload) - {"question", "context"}:
        raise QueryDenied("INVALID_REQUEST")
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise QueryDenied("INVALID_QUESTION")
    if any(ord(char) < 32 and char not in "\n\t" for char in question):
        raise QueryDenied("INVALID_QUESTION")
    context = payload.get("context", [])
    if not isinstance(context, list) or len(context) > MAX_CONTEXT:
        raise QueryDenied("INVALID_CONTEXT")
    for item in context:
        if not isinstance(item, dict) or set(item) != {"role", "text"}:
            raise QueryDenied("INVALID_CONTEXT")
        if item["role"] not in ("user", "assistant"):
            raise QueryDenied("INVALID_CONTEXT")
        if not isinstance(item["text"], str) or len(item["text"]) > MAX_QUESTION:
            raise QueryDenied("INVALID_CONTEXT")
    return {"question": question.strip(), "context": context, "principal_uid": uid}


def evidence_envelope(*, records, principal_uid, source_version):
    """Require independently authorized evidence, not user/model assertions."""
    if not isinstance(principal_uid, str) or not principal_uid:
        raise QueryDenied("AUTH_REQUIRED")
    if not isinstance(source_version, str) or not SAFE_ID.fullmatch(source_version):
        raise QueryDenied("SOURCE_VERSION_REQUIRED")
    if not isinstance(records, list) or len(records) > MAX_EVIDENCE:
        raise QueryDenied("EVIDENCE_LIMIT")
    result = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise QueryDenied("INVALID_EVIDENCE")
        if record.get("authorized_uid") != principal_uid:
            raise QueryDenied("CROSS_USER_EVIDENCE")
        key = record.get("source_id")
        if not isinstance(key, str) or not SAFE_ID.fullmatch(key) or key in seen:
            raise QueryDenied("INVALID_OR_DUPLICATE_SOURCE")
        if record.get("source_version") != source_version:
            raise QueryDenied("SOURCE_VERSION_CONFLICT")
        if record.get("authorized") is not True:
            raise QueryDenied("EVIDENCE_NOT_AUTHORIZED")
        seen.add(key)
        result.append({"source_id": key, "source_version": source_version})
    return result


def decimal_total(values):
    """Exact bounded arithmetic on plain decimal strings; no float conversion."""
    if not isinstance(values, (list, tuple)) or not values or len(values) > MAX_EVIDENCE:
        raise QueryDenied("AMOUNT_LIMIT")
    total = Decimal("0")
    parsed = []
    for value in values:
        # Reject exponential notation, huge integers and precision bombs before
        # Decimal parsing or formatting. Amounts are not rounded or rewritten.
        if (not isinstance(value, str) or len(value) > 64
                or not re.fullmatch(r"[+-]?[0-9]{1,18}(?:\.[0-9]{1,12})?", value)):
            raise QueryDenied("INVALID_AMOUNT")
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise QueryDenied("INVALID_AMOUNT") from exc
        if not number.is_finite():
            raise QueryDenied("INVALID_AMOUNT")
        parsed.append(number)
    # Maximum 18 integer + 12 fractional digits, plus carry from 20 terms.
    # Decimal default precision (28) would silently round valid inputs.
    with localcontext() as context:
        context.prec = 40
        for number in parsed:
            total += number
    return str(total)
