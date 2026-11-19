"""AWS Lightsail Phase 1: original dashboard v1.5 login + UI shell.

The dashboard UI is copied from the former Cloud Run source. Financial APIs,
imports, report exports, monitoring and user-management writes remain disabled.
Firebase Auth remains the original identity provider; credentials are held only
in private AWS host runtime mounts, never in GitHub or Docker images.
"""
import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
from dashboard_sessions import ORIGINS, PUBLIC_PATHS, install_sessions
from dashboard_login_pages import install_login_pages

SITE_ORIGIN = "https://sbi-preview.13-232-241-221.sslip.io"
UI_ROOT = Path(__file__).resolve().parent
# In the sealed Docker image, assets are alongside app.py; in the source
# checkout, tests load the same approved dashboard_source asset directory.
if not (UI_ROOT / "index.html").is_file():
    UI_ROOT = Path(__file__).resolve().parents[2] / "dashboard_source"

# Preserve approved Cloud Run origins while adding only this exact AWS HTTPS
# origin for CSRF; do not allow wildcard or arbitrary host-derived origins.
ORIGINS.add(SITE_ORIGIN)
PUBLIC_PATHS.add("/healthz")

app = Flask(__name__, static_folder=None)
install_sessions(app)
install_login_pages(app)
# Same Firebase session, separate read-only engineering Control Tower.
from tower_readonly import tower
app.register_blueprint(tower)


@app.after_request
def secure_ui(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/healthz")
def healthz():
    return jsonify(
        status="ok",
        service="sbi-aws-login-v150",
        financial_data_connected=False,
        financial_execution_enabled=False,
        imports_enabled=False,
        report_data_connected=False,
    )


@app.get("/")
@app.get("/dashboard")
def dashboard():
    # Entire original UI shell. Its legacy report/upload controls may render
    # but their API actions fail closed until individually migrated and approved.
    response = send_from_directory(str(UI_ROOT), "index.html")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    )
    return response


@app.get("/dashboard.js")
def dashboard_script():
    return send_from_directory(
        str(UI_ROOT), "dashboard.js", mimetype="application/javascript"
    )


@app.get("/account.js")
def account_script():
    return send_from_directory(
        str(UI_ROOT), "account.js", mimetype="application/javascript"
    )


@app.get("/dil_floating_assistant.js")
def assistant_script():
    return send_from_directory(
        str(UI_ROOT), "dil_floating_assistant.js",
        mimetype="application/javascript"
    )


@app.route("/api/<path:route>", methods=["GET", "HEAD", "POST", "PUT",
                                         "PATCH", "DELETE", "OPTIONS"])
def disabled_financial_api(route):
    return jsonify(
        error="Function not enabled in AWS Phase 1 login-only release",
        financial_execution_enabled=False,
    ), 403


@app.route("/users", methods=["GET", "HEAD"])
@app.route("/users.js", methods=["GET", "HEAD"])
def users_disabled():
    # User creation would modify Firebase; revisit in a dedicated approval.
    return jsonify(error="User administration is not enabled on AWS"), 403


@app.get("/pipeline")
def pipeline_not_on_login_service():
    # Caddy must send this route to the unchanged existing preview.
    return jsonify(error="Pipeline is served by the original AWS preview"), 404


if __name__ == "__main__":
    raise SystemExit("Run via the pinned non-root Gunicorn Docker image")
