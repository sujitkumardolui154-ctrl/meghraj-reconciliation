import os
import requests
from flask import Flask, jsonify, send_from_directory, g
from cloud_auth import get_backend_token
from sbi_report_access import can_view_report

app = Flask(__name__, static_folder=None)
BACKEND = "https://sbi-supervisor-backend-109590290120.asia-south1.run.app"
ENDPOINTS = {"health", "qa", "supervisor", "agents"}

@app.get("/")
def home():
    return send_from_directory(".", "index.html")

def fetch_monitoring(endpoint):
    if endpoint not in ENDPOINTS:
        raise ValueError("Endpoint not allowed")
    token = get_backend_token(BACKEND)
    response = requests.get(
        BACKEND + "/" + endpoint,
        headers={"Authorization": "Bearer " + token},
        timeout=15
    )
    response.raise_for_status()
    return response.json()

@app.get("/api/<endpoint>")
def monitoring_api(endpoint):
    if endpoint not in ENDPOINTS:
        return jsonify(error="Unknown endpoint"), 404
    try:
        return jsonify(fetch_monitoring(endpoint))
    except requests.RequestException:
        return jsonify(error="Supervisor API unavailable"), 502

@app.get("/dashboard.js")
def dashboard_script():
    return send_from_directory(".", "dashboard.js", mimetype="application/javascript")


# DIL v1.3.0 authenticated Excel upload
from flask import request
from werkzeug.exceptions import RequestEntityTooLarge

DASHBOARD_ORIGIN = "https://sbi-dashboard-109590290120.asia-south1.run.app"
EXCEL_LIMIT = 8 * 1024 * 1024

@app.post("/api/upload")
def excel_upload():
    request.max_content_length = EXCEL_LIMIT + 65536

    if (
        request.headers.get("Origin") not in {DASHBOARD_ORIGIN, "https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app"}
        or request.headers.get("X-DIL-Upload") != "1"
    ):
        return jsonify(error="Upload must come from this dashboard"), 403

    if request.mimetype != "multipart/form-data":
        return jsonify(error="Choose an Excel file"), 415

    try:
        files = request.files.getlist("file")
        if len(files) != 1 or set(request.files) != {"file"}:
            return jsonify(error="Choose exactly one Excel file"), 400

        uploaded = files[0]
        name = uploaded.filename or ""
        if not name.lower().endswith((".xlsx", ".xls")):
            return jsonify(error="Only .xlsx and .xls files are accepted"), 400
        if (
            len(name) > 180
            or "/" in name
            or "\\" in name
            or any(ord(c) < 32 for c in name)
        ):
            return jsonify(error="Invalid filename"), 400

        data = uploaded.stream.read(EXCEL_LIMIT + 1)
        if not data:
            return jsonify(error="The file is empty"), 400
        if len(data) > EXCEL_LIMIT:
            return jsonify(error="Maximum file size is 8 MiB"), 413
    except RequestEntityTooLarge:
        return jsonify(error="Maximum file size is 8 MiB"), 413

    try:
        token = get_backend_token(BACKEND)
    except Exception:
        app.logger.exception("Upload backend authentication failed")
        return jsonify(error="Backend authentication unavailable"), 503

    try:
        response = requests.post(
            BACKEND + "/upload",
            headers={"Authorization": "Bearer " + token},
            files={"file": (name, data, "application/octet-stream")},
            timeout=(10, 90),
            allow_redirects=False,
        )
    except requests.Timeout:
        return jsonify(
            error="Upload outcome unknown. Check the receipt before retrying."
        ), 504
    except requests.RequestException:
        return jsonify(
            error="Backend connection failed. Check upload status before retrying."
        ), 502

    if 300 <= response.status_code < 400:
        return jsonify(error="Unexpected backend redirect"), 502

    try:
        payload = response.json()
    except ValueError:
        return jsonify(error="Backend returned an invalid response"), 502

    if not isinstance(payload, dict):
        return jsonify(error="Backend returned an invalid response"), 502

    result = jsonify(payload)
    result.status_code = response.status_code
    result.headers["Cache-Control"] = "no-store"
    return result


# DIL v1.3.0 authenticated database reports
from flask import Response

REPORT_DOWNLOADS = {"unpaid", "ok", "error-value", "balance-review"}

def forward_database_report(kind=None):
    # Firebase authentication is installed globally below; these sensitive
    # report routes additionally require a dedicated explicit reader claim.
    if not can_view_report(getattr(g, "dil_user", None),
                           getattr(g, "dil_identity", None)):
        return jsonify(error="Report viewer permission required"), 403
    if kind is not None and kind not in REPORT_DOWNLOADS:
        return jsonify(error="Unknown report"), 404

    path = "/reports" if kind is None else "/reports/" + kind + ".csv"

    target = os.environ.get("REPORT_BACKEND", BACKEND).rstrip("/")
    try:
        token = get_backend_token(target)
    except Exception:
        app.logger.exception("Report backend authentication failed")
        return jsonify(error="Backend authentication unavailable"), 503

    try:
        upstream = requests.get(
            target + path,
            headers={"Authorization": "Bearer " + token},
            timeout=(10, 90),
            allow_redirects=False,
        )
    except requests.Timeout:
        return jsonify(error="Report request timed out. Please retry."), 504
    except requests.RequestException:
        return jsonify(error="Report backend unavailable"), 502

    if 300 <= upstream.status_code < 400:
        return jsonify(error="Unexpected backend redirect"), 502

    if upstream.status_code != 200:
        return jsonify(
            error="Report unavailable",
            backend_status=upstream.status_code,
        ), upstream.status_code if 400 <= upstream.status_code < 600 else 502

    content_type = upstream.headers.get("Content-Type", "").lower()

    if kind is None:
        if "application/json" not in content_type:
            return jsonify(error="Invalid report metadata response"), 502
        try:
            payload = upstream.json()
        except ValueError:
            return jsonify(error="Invalid report metadata"), 502
        if not isinstance(payload, dict):
            return jsonify(error="Invalid report metadata"), 502
        result = jsonify(payload)
    else:
        if not content_type.startswith("text/csv"):
            return jsonify(error="Backend did not return CSV"), 502
        result = Response(
            upstream.content,
            content_type="text/csv; charset=utf-8",
        )
        result.headers["Content-Disposition"] = (
            'attachment; filename="sbi-' + kind + '-v1.4.2.csv"'
        )
        count = upstream.headers.get("X-Report-Rows", "")
        if count.isdigit():
            result.headers["X-Report-Rows"] = count

    result.headers["Cache-Control"] = "no-store"
    result.headers["X-Content-Type-Options"] = "nosniff"
    return result

@app.get("/api/reports/reconciliation-changes")
@app.get("/api/reports/reconciliation-changes.csv")
def reconciliation_change_gateway():
    # Old/new invoice amounts require a stronger claim than ordinary reports.
    if not can_view_report(getattr(g, "dil_user", None),
                           getattr(g, "dil_identity", None), change_report=True):
        return jsonify(error="Reconciliation change viewer permission required"), 403
    from flask import request
    import re
    receipt = request.args.get("receipt", "")
    if not re.fullmatch(r"[a-f0-9]{32}", receipt):
        return jsonify(error="Invalid receipt"), 400
    is_csv = request.path.endswith(".csv")
    endpoint = "/change-reports.csv" if is_csv else "/change-reports"
    target = os.environ.get("CHANGE_BACKEND", BACKEND).rstrip("/")
    try:
        token = get_backend_token(target)
        upstream = requests.get(target + endpoint, params={"receipt": receipt},
            headers={"Authorization": "Bearer " + token}, timeout=(10,120),
            allow_redirects=False)
    except requests.RequestException:
        return jsonify(error="Change report backend unavailable"), 502
    except Exception:
        app.logger.exception("Change backend auth unavailable")
        return jsonify(error="Change report authentication unavailable"), 503
    if upstream.status_code != 200:
        return jsonify(error="Change report unavailable"), upstream.status_code if 400 <= upstream.status_code < 600 else 502
    content_type = upstream.headers.get("Content-Type", "").lower()
    if is_csv and not content_type.startswith("text/csv"):
        return jsonify(error="Unexpected CSV content"),502
    if not is_csv and "application/json" not in content_type:
        return jsonify(error="Unexpected report content"),502
    from flask import Response
    result = Response(upstream.content, content_type="text/csv; charset=utf-8" if is_csv else "application/json")
    if is_csv:
        result.headers["Content-Disposition"] = 'attachment; filename="reconciliation-changes.csv"'
    result.headers["Cache-Control"]="no-store"
    result.headers["X-Content-Type-Options"]="nosniff"
    return result

@app.get("/api/reports")
def database_report_index():
    return forward_database_report()

@app.get("/api/reports/<kind>.csv")
def database_report_download(kind):
    return forward_database_report(kind)


# DIL v1.4.0 database import gateway
import re
from flask import request
from werkzeug.exceptions import RequestEntityTooLarge

IMPORT_ORIGINS = {
    "https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://sbi-dashboard-109590290120.asia-south1.run.app",
    "https://sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://imports-v140---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
}
IMPORT_LIMIT = 8 * 1024 * 1024


def import_reply(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/imports/<path:part>", methods=["GET", "POST"])
def database_import_gateway(part):
    preview = part == "preview"
    match = re.fullmatch(r"([a-f0-9]{32})(?:/(rows|apply))?", part)
    if not preview and not match:
        return import_reply({"error": "Unknown import endpoint"}, 404)

    action = "preview" if preview else match.group(2)
    expected_method = "POST" if action in ("preview", "apply") else "GET"
    if request.method != expected_method:
        return import_reply({"error": "Method not allowed"}, 405)

    if expected_method == "POST":
        if (
            request.headers.get("Origin") not in IMPORT_ORIGINS
            or request.headers.get("X-DIL-Import") != "1"
        ):
            return import_reply(
                {"error": "Use the Database Update tab to submit imports"}, 403
            )

    params = {}
    files = None
    if action == "rows":
        cursor = request.args.get("after", "0")
        if not re.fullmatch(r"[0-9]{1,6}", cursor):
            return import_reply({"error": "Invalid page cursor"}, 400)
        params["after"] = cursor

    if preview:
        request.max_content_length = IMPORT_LIMIT + 65536
        if request.mimetype != "multipart/form-data":
            return import_reply({"error": "Choose an Excel file"}, 415)
        try:
            uploaded_files = request.files.getlist("file")
            if len(uploaded_files) != 1 or set(request.files) != {"file"}:
                return import_reply(
                    {"error": "Choose exactly one Excel file"}, 400
                )
            uploaded = uploaded_files[0]
            name = uploaded.filename or ""
            if not name.lower().endswith((".xlsx", ".xls")):
                return import_reply(
                    {"error": "Only .xlsx and .xls files are accepted"}, 400
                )
            if (
                len(name) > 180 or "/" in name or "\\" in name
                or any(ord(c) < 32 for c in name)
            ):
                return import_reply({"error": "Invalid filename"}, 400)
            data = uploaded.stream.read(IMPORT_LIMIT + 1)
            if not data:
                return import_reply({"error": "The file is empty"}, 400)
            if len(data) > IMPORT_LIMIT:
                return import_reply(
                    {"error": "Maximum file size is 8 MiB"}, 413
                )
            files = {"file": (name, data, "application/octet-stream")}
        except RequestEntityTooLarge:
            return import_reply(
                {"error": "Maximum file size is 8 MiB"}, 413
            )

    try:
        token = get_backend_token(BACKEND)
    except Exception:
        app.logger.exception("Import backend authentication failed")
        return import_reply(
            {"error": "Backend authentication unavailable"}, 503
        )

    try:
        response = requests.request(
            expected_method,
            os.environ.get("IMPORT_BACKEND", BACKEND).rstrip("/") + "/imports/" + part,
            headers={"Authorization": "Bearer " + token},
            params=params,
            files=files,
            timeout=(10, 120),
            allow_redirects=False,
        )
    except requests.Timeout:
        return import_reply({
            "error": (
                "Request timed out; outcome is unknown. "
                "Check the saved receipt before retrying. "
                "If preview returned no receipt, check server logs."
            )
        }, 504)
    except requests.RequestException:
        return import_reply({
            "error": "Backend connection failed. Check receipt status before retrying."
        }, 502)

    if 300 <= response.status_code < 400:
        return import_reply({"error": "Unexpected backend redirect"}, 502)
    try:
        payload = response.json()
    except ValueError:
        return import_reply({"error": "Backend returned an invalid response"}, 502)
    if not isinstance(payload, dict):
        return import_reply({"error": "Backend returned an invalid response"}, 502)
    return import_reply(payload, response.status_code)


# DIL authentication integration v1.5.0
from dashboard_sessions import install_sessions
from dashboard_login_pages import install_login_pages
from dashboard_users import install_user_management
from dashboard_account_pages import install_account_pages

install_sessions(app)
install_login_pages(app)
install_user_management(app)
install_account_pages(app)

# Read-only CREDIT NOTE reporting v1 — use the existing Firebase session guard.
# install_sessions(app) runs before this blueprint and populates g.dil_user
# only after revocation-checked Firebase cookie validation.
from sbi_credit_report_auth import create_credit_note_blueprint


def _authorize_credit_note_report():
    """Allow only an authenticated, enabled, explicitly entitled viewer."""
    user = getattr(g, "dil_user", None)
    identity = getattr(g, "dil_identity", None)
    if user is None or not isinstance(identity, dict):
        return False
    if user.disabled or user.uid != identity.get("uid"):
        return False
    claims = user.custom_claims or {}
    return (
        claims.get("dil_dashboard") is True
        and claims.get("sbi_credit_report_viewer") is True
    )


app.register_blueprint(create_credit_note_blueprint(_authorize_credit_note_report))
