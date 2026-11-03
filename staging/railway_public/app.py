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
    for entry in rows[:24]:
        writer.writerow((entry.get("kind", ""), entry.get("timestamp", ""),
                         entry.get("version", ""), entry.get("status", ""),
                         entry.get("title", ""), entry.get("url", "")))
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = 'attachment; filename="sbi-version-deployment-history.csv"'
    return response


@app.get("/api/pipeline/status")
def pipeline_status():
    snapshot = dict(current_pipeline())
    snapshot["deployed_build"] = build_identity()
    return jsonify(snapshot)


@app.route("/api/<path:subpath>",
           methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_financial_api(subpath):
    return {"error": "Financial API disabled in public preview"}, 403
