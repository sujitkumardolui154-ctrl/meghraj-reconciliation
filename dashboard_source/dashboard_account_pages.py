"""DIL v1.5.0 account UI; installed explicitly."""
from pathlib import Path
from flask import g, jsonify, send_from_directory
from dashboard_sessions import is_master

ROOT = Path(__file__).resolve().parent

def install_account_pages(app):
    if not app.extensions.get("dil_sessions"):
        raise RuntimeError("Install session protection first")

    @app.get("/users")
    def dil_users_page():
        user = getattr(g, "dil_user", None)
        if user is None or not is_master(user):
            return jsonify(error="Master administrator access required"), 403
        response = send_from_directory(str(ROOT), "users.html")
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/users.js")
    def dil_users_script():
        user = getattr(g, "dil_user", None)
        if user is None or not is_master(user):
            return jsonify(error="Master administrator access required"), 403
        return send_from_directory(
            str(ROOT), "users.js", mimetype="application/javascript"
        )

    @app.get("/account.js")
    def dil_account_script():
        return send_from_directory(
            str(ROOT), "account.js", mimetype="application/javascript"
        )
