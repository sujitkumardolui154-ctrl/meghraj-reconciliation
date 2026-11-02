"""DIL v1.5.0: master-only regular-user creation."""
import re
from firebase_admin import auth
from flask import g, jsonify, request
from dashboard_sessions import firebase_app, is_master, csrf_valid

def install_user_management(app):
    if not app.extensions.get("dil_sessions"):
        raise RuntimeError("Install session protection first")
    if app.extensions.get("dil_users"):
        raise RuntimeError("User management already installed")
    app.extensions["dil_users"] = True

    @app.post("/api/admin/users")
    def create_dashboard_user():
        user = getattr(g, "dil_user", None)
        if user is None or not is_master(user):
            return jsonify(error="Master administrator access required"), 403
        if not csrf_valid():
            return jsonify(error="Refresh the page and try again"), 403

        request.max_content_length = 8192
        if not request.is_json:
            return jsonify(error="JSON request required"), 415
        body = request.get_json(silent=True)
        if (
            not isinstance(body, dict)
            or set(body) != {"email", "password", "display_name"}
        ):
            return jsonify(error="Provide email, password and display name only"), 400

        email = body["email"]
        password = body["password"]
        name = body["display_name"]
        if not all(isinstance(value, str) for value in (email, password, name)):
            return jsonify(error="Invalid account details"), 400

        email = email.strip().lower()
        name = name.strip()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
            or any(ord(c) < 32 or ord(c) == 127 for c in email)
        ):
            return jsonify(error="Enter a valid email address"), 400
        if (
            not 1 <= len(name) <= 100
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
        ):
            return jsonify(error="Enter a display name of 1–100 characters"), 400
        if not 12 <= len(password) <= 128:
            return jsonify(error="Password must contain 12–128 characters"), 400

        try:
            created = auth.create_user(
                email=email,
                password=password,
                display_name=name,
                email_verified=False,
                disabled=True,
                app=firebase_app(),
            )
        except auth.EmailAlreadyExistsError:
            return jsonify(
                error="This email already exists. The existing account was not changed."
            ), 409
        except ValueError:
            return jsonify(error="Account details were rejected"), 400
        except Exception:
            return jsonify(
                error="Account creation outcome unknown. Check Identity Platform before retrying."
            ), 503

        try:
            auth.set_custom_user_claims(
                created.uid, {"dil_dashboard": True}, app=firebase_app()
            )
            auth.update_user(
                created.uid, disabled=False, app=firebase_app()
            )
            verified = auth.get_user(created.uid, app=firebase_app())
            if (
                verified.disabled
                or verified.uid != created.uid
                or (verified.email or "").lower() != email
                or (verified.custom_claims or {}) != {"dil_dashboard": True}
            ):
                raise RuntimeError("Account verification failed")
        except Exception:
            disabled_confirmed = False
            try:
                auth.update_user(
                    created.uid, disabled=True, app=firebase_app()
                )
                disabled_confirmed = auth.get_user(
                    created.uid, app=firebase_app()
                ).disabled is True
            except Exception:
                pass
            return jsonify(
                error="Account setup incomplete. Check this account before retrying.",
                uid=created.uid,
                disabled_confirmed=disabled_confirmed,
            ), 503

        return jsonify(
            ok=True,
            uid=verified.uid,
            email=verified.email,
            display_name=verified.display_name,
            administrator=False,
            message="Dashboard account created. Google IAP access is managed separately.",
        ), 201
