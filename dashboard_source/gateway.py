from datetime import timedelta
from pathlib import Path
import requests
import subprocess
from flask import jsonify, send_from_directory
BACKEND = "https://sbi-supervisor-backend-109590290120.asia-south1.run.app"
from flask import request, session, redirect, url_for, Flask
app = Flask(__name__)
app.secret_key = (Path(__file__).parent / ".flask_secret").read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax")

@app.get("/health")
def health():
    return {"status": "GATEWAY_READY"}

@app.get("/")
def home():
    return send_from_directory(".", "index.html")

@app.get("/api/status")
def status():
    return jsonify({"gateway": "READY", "backend": "NOT_CONNECTED", "financial_execution_enabled": False})

def fetch_backend(endpoint):
    token = subprocess.check_output(["gcloud", "auth", "print-identity-token"], text=True, timeout=15).strip()
    response = requests.get(BACKEND + "/" + endpoint, headers={"Authorization": "Bearer " + token}, timeout=20)
    response.raise_for_status()
    return response.json()

@app.before_request
def restrict_local_requests():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(error="Local access only"), 403

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

@app.before_request
def require_login():
    if request.path == "/health":
        return None
    if not session.get("authenticated", False):
        return jsonify(error="Authentication required"), 401
