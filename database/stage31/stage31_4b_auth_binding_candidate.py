"""Stage31.4B candidate trusted server-side auth binding. NOT deployed.

The real live Flask app MUST call dashboard_sessions.install_sessions(app)
before registering this Blueprint. This file is intentionally not included
in any live app entry point, and cannot authorize DB writes.
"""
from flask import g
from dashboard_sessions import csrf_valid, is_master
from stage31_4_private_preview import create_private_preview_blueprint

PRIVATE_PREVIEW_CLAIM = "sbi_invoice_intake_preview"

def verified_private_preview_user():
    """Require verified Firebase session objects from protect_dashboard.

    Headers, request query strings, and client-submitted user IDs are never
    used. This is a READ-ONLY PREVIEW role; it does not grant ingest/write.
    """
    user = getattr(g, "dil_user", None)
    identity = getattr(g, "dil_identity", None)
    if user is None or not isinstance(identity, dict):
        return False
    uid = getattr(user, "uid", None)
    if not isinstance(uid, str) or not uid or identity.get("uid") != uid:
        return False
    if not is_master(user):
        return False
    claims = getattr(user, "custom_claims", None)
    return isinstance(claims, dict) and claims.get(PRIVATE_PREVIEW_CLAIM) is True

def verified_private_preview_csrf():
    """Use the genuine session module CSRF function; do not fake/bypass it."""
    return csrf_valid()

def build_private_staging_preview_candidate():
    """Only for separately approved PRIVATE staging; NEVER auto-register live."""
    return create_private_preview_blueprint(
        auth_guard=verified_private_preview_user,
        csrf_guard=verified_private_preview_csrf,
    )
