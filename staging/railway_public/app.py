"""Isolated, password-protected SBI engineering dashboard. No financial API access."""
import csv
import hmac
import io
import os
import re
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_file

from pipeline_data import current_pipeline

app = Flask(__name__)


def authorized():
    username = os.environ.get("PREVIEW_USERNAME", "")
    password = os.environ.get("PREVIEW_PASSWORD", "")
    if not username or len(password) < 20:
        return False
    supplied = request.authorization
    return bool(supplied and hmac.compare_digest(supplied.username or "", username)
                and hmac.compare_digest(supplied.password or "", password))


@app.before_request
def require_preview_login():
    if request.path == "/healthz":
        return None
    if not authorized():
        return Response("Login required", 401, {
            "WWW-Authenticate": 'Basic realm="SBI private preview", charset="UTF-8"',
            "Cache-Control": "no-store",
        })


@app.after_request
def privacy_headers(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/healthz")
def health():
    return {"status": "ok", "financial_data_connected": False,
            "monitoring_mode": "read_only"}


@app.get("/")
@app.get("/pipeline")
def home():
    return send_file(Path(__file__).with_name("pipeline.html"),
                     mimetype="text/html; charset=utf-8")


def build_identity():
    sha = os.environ.get("SBI_SOURCE_SHA", "")
    channel = os.environ.get("SBI_RELEASE_CHANNEL", "")
    verified = bool(re.fullmatch(r"[0-9a-f]{40}", sha))
    return {
        "version": "git-" + sha[:12] if verified else "UNVERIFIED",
        "source_sha": sha if verified else None,
        "channel": channel if channel in ("aws-staging", "aws-public-preview") else "UNVERIFIED",
        "version_source": "docker_image_build_args" if verified else "not_stamped",
        "deployed_at_utc": None,
        "financial_api_connected": False,
    }


@app.get("/ui-preview")
def ui_preview():
    """Protected UI-only preview; the existing Basic Auth guard runs first."""
    response = send_file(Path(__file__).with_name("ui_preview.html"),
                         mimetype="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return response


@app.get("/ui-preview.css")
def ui_preview_css():
    """CSS is also protected by the global preview authentication guard."""
    return send_file(Path(__file__).with_name("ui_preview.css"),
                     mimetype="text/css; charset=utf-8")


@app.get("/api/pipeline/version")
def pipeline_version():
    return jsonify(build_identity())


@app.get("/api/pipeline/history.csv")
def pipeline_history_csv():
    snapshot = current_pipeline()
    rows = snapshot.get("activity", {}).get("events", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("Type", "Timestamp UTC", "Version", "Status", "Description", "GitHub evidence URL"))
    def safe_cell(value):
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or "\\t" in text or "\\r" in text else text
    for entry in rows[:24]:
        writer.writerow(tuple(safe_cell(entry.get(key, "")) for key in
                              ("kind", "timestamp", "version", "status", "title", "url")))
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="sbi-version-deployment-history.csv"'
    return response


@app.get("/api/pipeline/status")
def pipeline_status():
    snapshot = dict(current_pipeline())
    snapshot["deployed_build"] = build_identity()
    return jsonify(snapshot)



# Project-management-only editor. Never forwards to financial APIs or Firestore.
# In addition to the preview login, every write requires a separate owner key,
# same-origin JSON request and server-only issue-scoped GitHub credentials.
from urllib.parse import urlsplit
from priority_tasks import (
    InvalidTask, StaleTask, authorized as task_owner_authorized,
    enabled as task_editor_enabled, list_tasks as list_priority_tasks,
    retry_task as retry_priority_task, save_task as save_priority_task,
)


@app.get("/api/priority-tasks")
def get_priority_tasks():
    try:
        tasks = list_priority_tasks()
    except (OSError, ValueError, RuntimeError):
        return jsonify(error="Task database unavailable"), 503
    return jsonify(
        tasks=tasks, editor_available=task_editor_enabled(),
        source="dedicated_nonfinancial_sqlite", github="public_reviewable_issues",
        financial_database_connected=False,
    )


def _require_task_owner():
    if not task_editor_enabled():
        return jsonify(error="Owner task editor has not been configured"), 503
    origin = request.headers.get("Origin", "")
    parsed = urlsplit(origin)
    # Basic Auth alone is not a write permission; reject cross-site and
    # originless writes to prevent CSRF and accidental non-browser mutation.
    if (parsed.scheme not in ("https", "http")
            or parsed.netloc.lower() != request.host.lower()
            or parsed.path not in ("", "/")):
        return jsonify(error="Same-origin request required"), 403
    if not task_owner_authorized(request.headers.get("X-SBI-Task-Owner", "")):
        return jsonify(error="Task owner authorization required"), 403
    if request.content_length is not None and request.content_length > 8192:
        return jsonify(error="Task request too large"), 413
    if not request.is_json:
        return jsonify(error="JSON request required"), 415
    return None


def _task_reply(task, created=False):
    if task["sync_state"] != "synced":
        return jsonify(
            task=task, message="Saved to task database. GitHub pending: retry sync."
        ), 202
    return jsonify(task=task, message="Saved to task database and GitHub issue"), (
        201 if created else 200
    )


@app.post("/api/priority-tasks/unlock")
def unlock_priority_tasks():
    denial = _require_task_owner()
    if denial is not None:
        return denial
    return jsonify(owner_authorized=True, financial_writes=False)


@app.post("/api/priority-tasks")
def create_priority_task():
    denial = _require_task_owner()
    if denial is not None:
        return denial
    data = request.get_json(silent=True)
    try:
        task = save_priority_task(data)
    except InvalidTask as exc:
        return jsonify(error=str(exc)), 422
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Task database unavailable"), 503
    return _task_reply(task, created=True)


@app.patch("/api/priority-tasks/<task_id>")
def edit_priority_task(task_id):
    denial = _require_task_owner()
    if denial is not None:
        return denial
    data = request.get_json(silent=True)
    try:
        task = save_priority_task(data, task_id=task_id)
    except StaleTask:
        return jsonify(error="Task changed elsewhere; reload before editing"), 409
    except InvalidTask as exc:
        return jsonify(error=str(exc)), 422
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Task database unavailable"), 503
    return _task_reply(task)


@app.post("/api/priority-tasks/<task_id>/sync")
def retry_priority_task_sync(task_id):
    denial = _require_task_owner()
    if denial is not None:
        return denial
    try:
        task = retry_priority_task(task_id)
    except InvalidTask as exc:
        return jsonify(error=str(exc)), 404
    except (OSError, RuntimeError, ValueError):
        return jsonify(error="Task database unavailable"), 503
    return _task_reply(task)


@app.route("/api/<path:subpath>",
           methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_financial_api(subpath):
    return {"error": "Financial API disabled in public preview"}, 403
