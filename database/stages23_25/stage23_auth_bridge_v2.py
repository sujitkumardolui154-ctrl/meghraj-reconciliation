"""PR129 Stage 23: server-side reporting authorization bridge, v2.

Inputs are exclusively the Flask request context populated by
dashboard_sessions.protect_dashboard: g.dil_user and g.dil_identity.
The existing can_view_report policy makes the access decision.

No request headers, cookies, query parameters, alternate sessions or
developer bypasses are trusted. Missing/invalid context fails closed.
This is intended for the isolated candidate until authenticated QA passes.
"""
from __future__ import annotations

from flask import g


def authorize_postgres_report() -> bool:
    try:
        user = getattr(g, "dil_user", None)
        identity = getattr(g, "dil_identity", None)
        if user is None or not isinstance(identity, dict):
            return False

        from sbi_report_access import can_view_report
        return can_view_report(user, identity, change_report=False) is True
    except Exception:
        # Missing context, invalid claim/policy, or other authorization failure:
        # always deny; never leak session content into logs.
        return False
