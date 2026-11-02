"""Isolated public-URL, login-protected preview. NO SBI financial data/API."""
import hmac
import os
from flask import Flask, Response, request

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
            "Cache-Control": "no-store"
        })

@app.get("/healthz")
def health():
    return {"status": "ok", "financial_data_connected": False}

@app.get("/")
def home():
    return Response(
        "<!doctype html><html><head><meta charset='utf-8'><title>SBI Preview</title></head>"
        "<body><h1>SBI Reconciliation — Preview Only</h1>"
        "<p>Public URL, restricted login. Financial database and APIs are not connected.</p>"
        "<p>Migration is in progress. No invoice or payment data is available here.</p></body></html>",
        content_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    )

@app.route("/api/<path:subpath>", methods=["GET","POST","PUT","PATCH","DELETE"])
def disabled_api(subpath):
    return {"error": "Financial API disabled in public preview"}, 403
