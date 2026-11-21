"""Stage 23 candidate-only authorization bridge.

Uses ONLY the existing can_view_report policy and server-side Flask.g context.
No shared secret, header, query parameter, or alternate login route.

This code deliberately FAILS CLOSED if actual PR129 session attributes or
policy function signature differ. Those differences must be mapped/reviewed,
not bypassed. It is not proof of an authenticated end-to-end session.
"""
from __future__ import annotations

import inspect
from flask import g


def authorize_postgres_report() -> bool:
    user = getattr(g, "user", None)
    identity = getattr(g, "identity", None)
    if user is None or not isinstance(identity, dict):
        return False

    try:
        from sbi_report_access import can_view_report

        signature = inspect.signature(can_view_report)
        names = list(signature.parameters)
        if names == ["user", "identity", "change_report"]:
            return can_view_report(user, identity, change_report=False) is True
        if names == ["user", "identity"]:
            return can_view_report(user, identity) is True
    except Exception:
        # Deny, never grant on missing session data, invalid signatures,
        # invalid claims or internal authorization errors.
        return False
    return False
