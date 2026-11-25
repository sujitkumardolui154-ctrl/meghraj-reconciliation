"""R31.12 private-only Firebase authentication and session QA.

Receives two existing Firebase ID tokens on stdin. No account creation, Firebase
claim edits, PostgreSQL writes, receipt fixtures, public Caddy route or deploy.
Only fixed, non-sensitive receipt codes are sent to stdout.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlparse

from firebase_admin import auth
from app import app, SITE_ORIGIN
from dashboard_sessions import firebase_app, MASTER_UID, SESSION_COOKIE

DOMAIN = urlparse(SITE_ORIGIN).hostname
BASE = {"base_url": SITE_ORIGIN}


def emit(key: str, value: str) -> None:
    print("DB_R31_12_" + key + "=" + value, flush=True)


def private_session(id_token: str, expected_uid: str) -> bool:
    """Exercise local Flask CSRF, Firebase session creation and private status."""
    client = app.test_client()
    csrf_result = client.get("/auth/csrf", **BASE)
    body = csrf_result.get_json(silent=True)
    csrf = body.get("csrf_token") if isinstance(body, dict) else None
    if csrf_result.status_code != 200 or not isinstance(csrf, str) or len(csrf) != 64:
        return False
    login = client.post(
        "/auth/session", json={"idToken": id_token},
        headers={"Origin": SITE_ORIGIN, "X-DIL-CSRF": csrf},
        **BASE
    )
    if login.status_code != 200:
        return False
    cookie = client.get_cookie(SESSION_COOKIE, domain=DOMAIN)
    if cookie is None:
        return False
    claims = auth.verify_session_cookie(
        cookie.value, check_revoked=True, app=firebase_app()
    )
    if claims.get("uid") != expected_uid:
        return False
    return client.get("/api/r31-private-qa/status", **BASE).status_code == 200


def main() -> int:
    raw = sys.stdin.buffer.read(30001)
    if not raw or len(raw) > 30000:
        emit("AUTH_INPUT", "BLOCKED_LENGTH")
        return 2
    try:
        document = json.loads(raw)
    except (ValueError, UnicodeError, TypeError):
        emit("AUTH_INPUT", "BLOCKED_FORMAT")
        return 2
    tokens = document.get("id_tokens") if isinstance(document, dict) else None
    if (not isinstance(tokens, list) or len(tokens) != 2
            or any(type(t) is not str or not (200 <= len(t) <= 12000)
                   for t in tokens)):
        emit("AUTH_INPUT", "BLOCKED_TWO_TOKENS_REQUIRED")
        return 2
    try:
        sdk = firebase_app()
        claims = [
            auth.verify_id_token(t, check_revoked=True, app=sdk)
            for t in tokens
        ]
        uids = [c.get("uid") for c in claims]
        if any(not isinstance(uid, str) or not uid for uid in uids):
            emit("VERIFIED_TOKENS", "BLOCKED_UID_MISSING")
            return 2
        users = [auth.get_user(uid, app=sdk) for uid in uids]
        if any(user.disabled for user in users):
            emit("VERIFIED_TOKENS", "BLOCKED_DISABLED_USER")
            return 2
        if any((user.custom_claims or {}).get("dil_dashboard") is not True
               for user in users):
            emit("VERIFIED_TOKENS", "BLOCKED_DASHBOARD_CLAIM")
            return 2
        if uids[0] != MASTER_UID:
            emit("VERIFIED_TOKENS", "BLOCKED_ACCOUNT_1_NOT_MASTER")
            return 2
        if uids[1] == MASTER_UID or uids[0] == uids[1]:
            emit("VERIFIED_TOKENS", "BLOCKED_SAME_UID")
            return 2
        if (users[1].custom_claims or {}).get("dil_admin") is True:
            emit("VERIFIED_TOKENS", "BLOCKED_SECOND_ADMIN_CLAIM")
            return 2
        emit("VERIFIED_TOKENS", "PASS_DISTINCT_MASTER_AND_SECOND")
        if not private_session(tokens[0], uids[0]):
            emit("PRIVATE_APP_SESSIONS", "BLOCKED_MASTER_SESSION")
            return 2
        if not private_session(tokens[1], uids[1]):
            emit("PRIVATE_APP_SESSIONS", "BLOCKED_SECOND_SESSION")
            return 2
    except Exception:
        # Never expose exception contents: provider errors can contain identities.
        emit("VERIFICATION", "BLOCKED_PRIVATE_RUNTIME")
        return 2
    emit("PRIVATE_APP_SESSIONS", "PASS_BOTH_INDEPENDENT")
    emit("FINANCIAL_WRITES", "NONE_BY_TEST")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
