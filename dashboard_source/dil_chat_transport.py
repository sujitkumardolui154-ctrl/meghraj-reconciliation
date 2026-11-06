"""Authenticated DIL transport endpoint; intentionally NO database/model connection.

Security posture: a request is eligible only after dashboard_sessions installed
the revocation-checked session middleware. The endpoint then demands the exact
user identity, an explicit invoice reader entitlement, CSRF, and bounded JSON.
No user-supplied identity/roles are trusted. Until a separately reviewed read-
only retrieval service is ready, authorized queries receive a truthful 503.
"""
from flask import Blueprint, g, jsonify, request
from dashboard_sessions import csrf_valid

dil_chat = Blueprint("dil_chat", __name__)
MAX_REQUEST_BYTES = 16384
MAX_QUESTION_LENGTH = 2000


def _reply(message, status):
    response = jsonify(error=message)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def invoice_reader_authorized(user, identity):
    """Require *both* verified session UID and explicit current user claim."""
    if user is None or not isinstance(identity, dict):
        return False
    if not isinstance(identity.get("uid"), str) or user.uid != identity["uid"]:
        return False
    if getattr(user, "disabled", True):
        return False
    claims = getattr(user, "custom_claims", None)
    return (
        isinstance(claims, dict)
        and claims.get("dil_dashboard") is True
        and claims.get("sbi_invoice_reader") is True
    )


@dil_chat.post("/api/dil/chat")
def invoice_chat():
    """Authenticated transport seam only; no live invoice retrieval."""
    request.max_content_length = MAX_REQUEST_BYTES
    if not invoice_reader_authorized(
        getattr(g, "dil_user", None),
        getattr(g, "dil_identity", None),
    ):
        return _reply("Invoice chatbot permission required", 403)
    if not csrf_valid():
        return _reply("Invalid CSRF token", 403)
    if request.mimetype != "application/json":
        return _reply("JSON content type required", 415)
    if request.content_length is None or request.content_length > MAX_REQUEST_BYTES:
        return _reply("Request size invalid", 413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"question"}:
        return _reply("Invalid chat request", 400)
    q = body["question"]
    if (not isinstance(q, str) or not q.strip()
            or len(q) > MAX_QUESTION_LENGTH
            or any(ord(c) < 32 and c not in "\n\t" for c in q)):
        return _reply("Invalid invoice question", 400)
    # Intentionally not connected to any database, financial engine or LLM.
    return _reply("Verified read-only invoice retrieval is not connected", 503)
