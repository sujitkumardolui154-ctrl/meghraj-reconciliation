"""Authenticated, read-only restoration of the original SBI engineering Control Tower.

Reuses the original staging/railway_public/pipeline.html and its GitHub-only
status reader. No financial API, SQLite task editor or write permission is
carried into the Firebase login app.
"""
import csv
import io
import os
import re
from pathlib import Path

from flask import Blueprint, Response, jsonify
from pipeline_data import current_pipeline

tower = Blueprint("sbi_control_tower", __name__)


def _html_path():
    bundled = Path(__file__).resolve().parent / "pipeline.html"
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parents[2] / "staging/railway_public/pipeline.html"


def _release_identity():
    sha = os.environ.get("SBI_SOURCE_SHA", "")
    verified = bool(re.fullmatch(r"[0-9a-f]{40}", sha))
    return {
        "version": "git-" + sha[:12] if verified else "UNVERIFIED",
        "source_sha": sha if verified else None,
        "channel": "aws-authenticated-control-tower",
        "version_source": "docker_image_build_args" if verified else "not_stamped",
        "deployed_at_utc": None,
        "financial_api_connected": False,
    }


@tower.get("/control-tower")
def control_tower():
    # Preserve the verified original layout and source-backed JavaScript.
    # Move its read-only API requests behind this app's Firebase session
    # instead of using the independent Basic Auth /pipeline service.
    source = _html_path().read_text(encoding="utf-8")
    if ('All stages. One control center.' not in source
            or '"/api/pipeline/status"' not in source):
        return jsonify(error="Original Control Tower source contract changed"), 503
    source = source.replace("/api/pipeline/", "/control-tower/api/pipeline/")
    source = source.replace("/api/priority-tasks", "/control-tower/api/priority-tasks")
    source = source.replace(
        '<div class="head-actions">',
        '<div class="head-actions">'
        '<a class="btn" href="/dashboard" style="text-decoration:none">'
        '← Dashboard</a>',
        1,
    )
    response = Response(source, mimetype="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'none'"
    )
    return response


@tower.get("/control-tower/api/pipeline/status")
def tower_status():
    status = dict(current_pipeline())
    status["deployed_build"] = _release_identity()
    return jsonify(status)


@tower.get("/control-tower/api/pipeline/version")
def tower_version():
    return jsonify(_release_identity())


@tower.get("/control-tower/api/pipeline/history.csv")
def tower_history():
    events = current_pipeline().get("activity", {}).get("events", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("Type", "Timestamp UTC", "Version", "Status",
                     "Description", "GitHub evidence URL"))
    for entry in events[:24]:
        if not isinstance(entry, dict):
            continue
        row = [str(entry.get(key, "") or "")
               for key in ("kind", "timestamp", "version", "status", "title", "url")]
        # Prevent spreadsheet formula injection when exported CSV is opened.
        row = ["'" + value if value.lstrip().startswith(("=", "+", "-", "@"))
               or "\t" in value or "\r" in value else value for value in row]
        writer.writerow(row)
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        'attachment; filename="sbi-control-tower-history.csv"'
    )
    return response


@tower.get("/control-tower/api/priority-tasks")
def editor_data_unavailable():
    # The legacy SQLite/GitHub task editor is NOT migrated into Firebase
    # permissions. Do not represent inaccessible tasks as an empty register.
    return jsonify(
        error="Legacy owner task database not connected; read-only only",
        editor_available=False,
        financial_database_connected=False,
    ), 503


@tower.route("/control-tower/api/<path:route>",
             methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def reject_tower_writes(route):
    return jsonify(
        error="Control Tower is read-only; task editing and financial writes blocked",
        financial_execution_enabled=False,
    ), 403
