"""Private read-only SBI CREDIT NOTE canary, distinct from financial gateway."""
import os
from flask import Flask, g, jsonify, request
from firebase_admin import auth
from dashboard_sessions import SESSION_COOKIE, firebase_app
from sbi_credit_report_auth import create_credit_note_blueprint

app = Flask(__name__)

@app.after_request
def safety_headers(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.get("/health")
def health():
    return jsonify(service="sbi-reporting-private-canary", finance="RESTRICTED", database_writes=False)

def authorize_report_view():
    """Verify a revoked-aware Firebase session for every report request."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return False
    try:
        identity = auth.verify_session_cookie(cookie, check_revoked=True, app=firebase_app())
        user = auth.get_user(identity["uid"], app=firebase_app())
    except Exception:
        return False
    claims = user.custom_claims or {}
    return (
        not user.disabled
        and claims.get("dil_dashboard") is True
        and claims.get("sbi_report_viewer") is True
        and user.uid == identity.get("uid")
    )

app.register_blueprint(create_credit_note_blueprint(authorize_report_view))
