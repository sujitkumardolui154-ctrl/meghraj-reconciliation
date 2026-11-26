"""AWS Lightsail Phase 1: original dashboard v1.5 login + UI shell.

The dashboard UI is copied from the former Cloud Run source. Financial APIs,
imports, report exports, monitoring and user-management writes remain disabled.
Firebase Auth remains the original identity provider; credentials are held only
in private AWS host runtime mounts, never in GitHub or Docker images.
"""
import os
import sys
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

@app.after_request
def permit_same_origin_tower_embed(response):
    # Registered before session hooks so this narrowly scoped override runs
    # last. Standalone pages and every other route retain DENY.
    from flask import request
    if request.path == "/control-tower" and request.args.get("embedded") == "1":
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response

install_sessions(app)
install_login_pages(app)
# Same Firebase session, separate read-only engineering Control Tower.
# Support original source-level tests while Docker loads assets from /app.
_source_file = Path(__file__).resolve()
_source_dirs = [_source_file.parent]
# Source checkout has a repository root; compact /app Docker layout does not.
if len(_source_file.parents) > 2:
    _source_dirs.append(_source_file.parents[2] / "staging/railway_public")
for _path in _source_dirs:
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
from tower_readonly import tower
app.register_blueprint(tower)
# User-owned project notes/tasks are separate from financial database APIs.
from project_workspace import workspace
app.register_blueprint(workspace)
# Controlled payment evidence upload + fixed-header preview; financial execution stays disabled.
from payment_evidence_upload import payment_evidence
app.register_blueprint(payment_evidence)
# R31: private, owner-scoped payment received ledger reports (not settlement).
from payment_received_reports import payment_received_reports
app.register_blueprint(payment_received_reports)
# Strict nonfinancial receipt-to-engine readiness gate; no allocation runner.
from reconciliation_readiness import reconciliation_readiness
app.register_blueprint(reconciliation_readiness)

# R31.6: Firebase-authenticated source-only PostgreSQL QA routes.
# Feature flag exists only in the privately staged QA Docker container.
# No Caddy route, no financial engine, no public release by default.
if os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED") == "isolated-ownerqa-firebase-csrf-v1":
    from r31_stage_blueprint import stage_r31
    app.register_blueprint(stage_r31)

    # R31.11.3: disabled by default; new isolated candidate image only.
    # Requires signed-in Firebase UID -> dedicated restricted PG LOGIN role.
    if os.environ.get("SBI_R31_11_3_RUNTIME_ENABLED") == "private-firebase-rls-readonly-v1":
        from r31_11_3_runtime_rls_blueprint import runtime_tenant_rls
        app.register_blueprint(runtime_tenant_rls)

    # R31.11.4: a distinct, never-public private acceptance candidate.
    # No DB privilege/user creation or Caddy routing is performed here.
    if os.environ.get("SBI_R31_11_4_RUNTIME_ENABLED") == "private-firebase-rls-auth-acceptance-v1":
        from r31_11_4_runtime_rls_blueprint import runtime_tenant_rls as runtime_r3114
        app.register_blueprint(runtime_r3114)


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
        "connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    )
    return response


@app.get("/dashboard-theme.css")
def dashboard_theme_css():
    return send_from_directory(
        str(UI_ROOT), "dashboard_theme.css", mimetype="text/css"
    )


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
