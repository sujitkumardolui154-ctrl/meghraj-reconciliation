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

from flask import Blueprint, Response, jsonify, request, send_from_directory
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
    embedded = request.args.get("embedded") == "1"
    if embedded:
        # Only the same-origin dashboard may frame the compact view.
        # Keep the historical full-page Control Tower intact at /control-tower.
        compact_style = (
            '<style id="control-tower-embedded-style">'
            "header.top{display:none!important}"
            ".hero{padding-top:18px!important}"
            ".shell{padding-left:14px;padding-right:14px}"
            "</style>"
        )
        source = source.replace("</head>", compact_style + "</head>", 1)
    # Keep historical source intact; overlay the professional theme and
    # append the separate authenticated private workspace component.
    theme_link = '<link rel="stylesheet" href="/control-tower/theme.css">'
    source = source.replace("</head>", theme_link + "</head>", 1)
    old_section_start = source.find('    <div class="section-head" style="margin-top:22px">')
    old_section_end = source.find('    <p class="sub">Priority order is the agreed development plan.', old_section_start)
    if old_section_start < 0 or old_section_end < 0:
        return jsonify(error="Legacy task UI contract changed"), 503
    source = (source[:old_section_start] + '<div id="legacy-owner-task-interface" hidden>'
              + source[old_section_start:old_section_end] + '</div>\n'
              + source[old_section_end:])
    ui_file = Path(__file__).resolve().parent / "workspace_ui.html"
    if not ui_file.is_file():
        return jsonify(error="Private project workspace UI missing"), 503
    source = source.replace(
        '  <section class="section" id="pipeline">',
        ui_file.read_text(encoding="utf-8") + '\n  <section class="section" id="pipeline">', 1,
    )
    board_file = Path(__file__).resolve().parent / "github_workstream_board.html"
    if not board_file.is_file():
        return jsonify(error="GitHub workstream task board asset missing"), 503
    source = source.replace(
        '  <section class="section two" id="obstructions">',
        board_file.read_text(encoding="utf-8") +
        '\n  <section class="section two" id="obstructions">', 1,
    )
    # The historical read-only refresh loop is kept, but it now runs every
    # 10 minutes and distributes the same authenticated snapshot to the
    # combined workstream board. The source register cannot be mutated.
    original = 'refresh();setInterval(refresh,90000);'
    original_render = 'current=data;var register=data.register;var available=register && register.available;'
    if original not in source or original_render not in source:
        return jsonify(error="Control Tower GitHub refresh contract changed"), 503
    source = source.replace(original, 'refresh();setInterval(refresh,600000);', 1)
    source = source.replace(original_render, original_render +
        '\n    window.dispatchEvent(new CustomEvent("sbi-github-snapshot",{detail:data}));', 1)
    source = source.replace(
        '$("last-sync").textContent="Refresh failed: "+err.message;',
        '$("last-sync").textContent="Refresh failed: "+err.message;'
        'window.dispatchEvent(new CustomEvent("sbi-github-refresh-error",{detail:err.message}));',
        1,
    )
    source = source.replace('refresh every 90s', 'refresh every 10 minutes')
    source = source.replace('90-second browser refresh, up to 5-minute server cache',
                            '10-minute browser refresh, up to 10-minute GitHub cache')
    source = source.replace('Automatically refreshes every 90 seconds',
                            'Automatically refreshes every 10 minutes')

    response = Response(source, mimetype="text/html; charset=utf-8")
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors " + ("'self'" if embedded else "'none'") + "; base-uri 'none'; "
        "form-action 'none'"
    )
    return response


@tower.get("/control-tower/theme.css")
def tower_css():
    return send_from_directory(str(Path(__file__).resolve().parent),
                               "tower_theme.css", mimetype="text/css")


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
