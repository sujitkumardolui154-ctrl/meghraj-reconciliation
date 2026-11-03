"""Isolated, password-protected SBI engineering dashboard. No financial API access."""
import hmac
import os
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


@app.get("/api/pipeline/status")
def pipeline_status():
    return jsonify(current_pipeline())


@app.route("/api/<path:subpath>",
           methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def disabled_financial_api(subpath):
    return {"error": "Financial API disabled in public preview"}, 403
