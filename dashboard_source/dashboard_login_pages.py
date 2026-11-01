"""DIL animated login page v1.5.0; installed explicitly."""
import os
from pathlib import Path
from flask import jsonify, send_from_directory

ROOT = Path(__file__).resolve().parent

def install_login_pages(app):
    if app.extensions.get("dil_login_pages"):
        raise RuntimeError("Login pages already installed")
    app.extensions["dil_login_pages"] = True

    @app.get("/login")
    def dil_login_page():
        response = send_from_directory(str(ROOT), "login.html")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "script-src 'self'; style-src 'self'; "
            "connect-src 'self' https://identitytoolkit.googleapis.com; "
            "img-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/login.css")
    def dil_login_css():
        return send_from_directory(
            str(ROOT), "login.css", mimetype="text/css"
        )

    @app.get("/login.js")
    def dil_login_js():
        return send_from_directory(
            str(ROOT), "login.js", mimetype="application/javascript"
        )

    @app.get("/auth/config")
    def dil_login_config():
        key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
        if not key:
            response = jsonify(error="Login configuration is not ready")
            response.status_code = 503
        else:
            response = jsonify(apiKey=key, version="1.5.0")
        response.headers["Cache-Control"] = "no-store"
        return response
