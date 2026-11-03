"""Fail-closed, independent import caller verification for Cloud Run or AWS.

This does not authorize a dashboard user. User-level import claims must be
checked at the trusted gateway; the backend authenticates ONLY that gateway's
service identity before exposing Firestore-backed import routes.

SBI_IMPORT_AUDIENCE: exact OIDC audience for this backend.
SBI_IMPORT_CALLER_EMAIL: exact permitted gateway service-account email.
Unset settings deny all requests. No anonymous or header-identity fallback.
"""
import os


def authorized_import_caller(request, *, verifier=None, audience=None, caller_email=None):
    audience = audience if audience is not None else os.environ.get("SBI_IMPORT_AUDIENCE", "")
    caller_email = caller_email if caller_email is not None else os.environ.get("SBI_IMPORT_CALLER_EMAIL", "")
    if not audience.startswith("https://") or not caller_email.endswith(".gserviceaccount.com"):
        return False

    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer ") or len(value) > 12000:
        return False
    token = value[7:]
    if not token or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in token):
        return False

    try:
        if verifier is None:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
            claims = id_token.verify_oauth2_token(token, Request(), audience=audience)
        else:
            claims = verifier(token, audience)
    except Exception:
        return False

    return (
        isinstance(claims, dict)
        and claims.get("aud") == audience
        and claims.get("email") == caller_email
        and claims.get("email_verified") is True
        and claims.get("iss") in ("https://accounts.google.com", "accounts.google.com")
    )
