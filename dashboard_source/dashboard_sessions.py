"""DIL dashboard authentication v1.5.0 — installed explicitly."""
import secrets
import time
from datetime import timedelta

import firebase_admin
from firebase_admin import auth
from flask import g, jsonify, redirect, request
from stage6_origin_policy import is_allowed_origin

PROJECT = "meghraj-reconciliation"
MASTER_UID = "bcaH2nt62se1D6pZvTFAvW5UO3B2"
MASTER_EMAIL = "sujitkumardolui154@gmail.com"
SESSION_COOKIE = "__Host-dil_session"
CSRF_COOKIE = "__Host-dil_csrf"
SESSION_SECONDS = 8 * 60 * 60

ORIGINS = {
    "https://login-v150---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://sbi-dashboard-109590290120.asia-south1.run.app",
    "https://sbi-dashboard-ahz6wqeiaq-el.a.run.app",
    "https://imports-v140---sbi-dashboard-ahz6wqeiaq-el.a.run.app",
}

PUBLIC_PATHS = {
    "/login",
    "/login.js",
    "/login.css",
    "/auth/config",
    "/auth/csrf",
    "/auth/session",
}

def firebase_app():
    try:
        return firebase_admin.get_app("dil-dashboard")
    except ValueError:
        return firebase_admin.initialize_app(
            options={"projectId": PROJECT},
            name="dil-dashboard",
        )

def is_master(user):
    claims = user.custom_claims or {}
    return (
        user.uid == MASTER_UID
        and (user.email or "").lower() == MASTER_EMAIL
        and claims.get("dil_admin") is True
        and claims.get("dil_dashboard") is True
        and not user.disabled
    )

def csrf_valid():
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("X-DIL-CSRF", "")
    return (
        is_allowed_origin(request.headers.get("Origin"))
        and len(cookie) == 64
        and len(header) == 64
        and secrets.compare_digest(cookie, header)
    )

def set_cookie(response, name, value, max_age):
    response.set_cookie(
        name, value,
        max_age=max_age,
        secure=True,
        httponly=True,
        samesite="Lax",
        path="/",
    )

def clear_cookie(response, name):
    response.delete_cookie(
        name, path="/", secure=True,
        httponly=True, samesite="Lax",
    )

def install_sessions(app):
    if app.extensions.get("dil_sessions"):
        raise RuntimeError("Session protection already installed")
    app.extensions["dil_sessions"] = True

    @app.after_request
    def session_response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.before_request
    def protect_dashboard():
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not is_allowed_origin(request.headers.get("Origin")):
                return jsonify(error="Untrusted request origin"), 403

        if request.path in PUBLIC_PATHS:
            return None

        cookie = request.cookies.get(SESSION_COOKIE, "")
        if not cookie:
            if request.path == "/" and request.method == "GET":
                return redirect("/login", code=303)
            return jsonify(error="Login required"), 401

        try:
            identity = auth.verify_session_cookie(
                cookie, check_revoked=True, app=firebase_app()
            )
            user = auth.get_user(identity["uid"], app=firebase_app())
        except (
            auth.InvalidSessionCookieError,
            auth.RevokedSessionCookieError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
            ValueError,
        ):
            response = jsonify(error="Session expired. Please sign in again.")
            response.status_code = 401
            clear_cookie(response, SESSION_COOKIE)
            return response
        except Exception:
            return jsonify(error="Authentication service unavailable"), 503

        if user.disabled or (user.custom_claims or {}).get("dil_dashboard") is not True:
            return jsonify(error="Dashboard access is not enabled"), 403

        g.dil_user = user
        g.dil_identity = identity
        return None

    @app.get("/auth/csrf")
    def session_csrf():
        token = secrets.token_hex(32)
        response = jsonify(csrf_token=token)
        set_cookie(response, CSRF_COOKIE, token, SESSION_SECONDS)
        return response

    @app.post("/auth/session")
    def session_login():
        request.max_content_length = 16384
        if not csrf_valid():
            return jsonify(error="Refresh the login page and try again"), 403
        if not request.is_json:
            return jsonify(error="JSON request required"), 415

        body = request.get_json(silent=True)
        token = body.get("idToken") if isinstance(body, dict) else None
        if not isinstance(token, str) or not 1 <= len(token) <= 12000:
            return jsonify(error="Invalid login request"), 400

        try:
            identity = auth.verify_id_token(
                token, check_revoked=True, app=firebase_app()
            )
            authenticated_at = identity.get("auth_time")
            if (
                not isinstance(authenticated_at, (int, float))
                or not 0 <= time.time() - authenticated_at <= 300
                or identity.get("firebase", {}).get("sign_in_provider") != "password"
            ):
                return jsonify(error="Please sign in again with your password"), 401

            user = auth.get_user(identity["uid"], app=firebase_app())
            if (
                user.disabled
                or (user.custom_claims or {}).get("dil_dashboard") is not True
            ):
                return jsonify(error="Dashboard access is not enabled"), 403

            cookie = auth.create_session_cookie(
                token,
                expires_in=timedelta(seconds=SESSION_SECONDS),
                app=firebase_app(),
            )
        except (
            auth.InvalidIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
            auth.UserNotFoundError,
            ValueError,
        ):
            return jsonify(error="Invalid login. Please sign in again."), 401
        except Exception:
            return jsonify(error="Authentication service unavailable"), 503

        response = jsonify(ok=True, administrator=is_master(user))
        set_cookie(response, SESSION_COOKIE, cookie, SESSION_SECONDS)
        return response

    @app.get("/auth/me")
    def session_identity():
        user = g.dil_user
        return jsonify(
            email=user.email,
            display_name=user.display_name or "",
            administrator=is_master(user),
        )

    @app.post("/auth/logout")
    def session_logout():
        if not csrf_valid():
            return jsonify(error="Refresh the page and try again"), 403
        try:
            auth.revoke_refresh_tokens(g.dil_user.uid, app=firebase_app())
        except Exception:
            response = jsonify(
                error="Local session cleared; server revocation could not be confirmed"
            )
            response.status_code = 503
        else:
            response = jsonify(ok=True)
        clear_cookie(response, SESSION_COOKIE)
        clear_cookie(response, CSRF_COOKIE)
        return response
