"""Inert, opt-in SBI Credit Note upload preview HTTP blueprint.

This module NEVER registers itself into production_gateway or any running
application. The staging host must explicitly register the blueprint only
after dashboard_sessions.install_sessions(app), with a read-only handler.
No financial writer, apply method, receipt mutation, or import approval.
"""
import os
from flask import Blueprint, Response, current_app, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

MAX_BYTES = 8 * 1024 * 1024
ROLE = "sbi_credit_note_import_preview"
FEATURE_FLAG = "SBI_CN_STAGING_PREVIEW_ENABLED"


def can_preview_credit_note(user, identity):
    """A verified Firebase session plus a specific entitlement are required."""
    if user is None or not isinstance(identity, dict):
        return False
    uid = getattr(user, "uid", None)
    if not isinstance(uid, str) or not uid or identity.get("uid") != uid:
        return False
    if getattr(user, "disabled", True) is not False:
        return False
    claims = getattr(user, "custom_claims", None)
    return (
        isinstance(claims, dict)
        and claims.get("dil_dashboard") is True
        and claims.get(ROLE) is True
    )


def _response(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def create_credit_note_staging_blueprint(preview_handler):
    """Build a staging-only endpoint with explicit dependency injection.

    preview_handler(filename, bytes) must perform read-only registry queries
    using a separately restricted staging identity. No default database client
    is constructed by this module.
    """
    if not callable(preview_handler):
        raise ValueError("Explicit staging read-only preview handler required")
    bp = Blueprint("sbi_cn_staging_preview_v1", __name__)

    @bp.post("/staging/credit-note/import-preview")
    def credit_note_preview():
        # Never enable on a normal production runtime or via a URL alone.
        if os.environ.get(FEATURE_FLAG) != "true":
            return _response({"error": "STAGING_PREVIEW_DISABLED"}, 503)
        if current_app.extensions.get("dil_sessions") is not True:
            return _response({"error": "VERIFIED_SESSION_MIDDLEWARE_REQUIRED"}, 503)

        # In the real gateway these g values are populated only by verified,
        # non-revoked Firebase sessions installed before this Blueprint.
        if not can_preview_credit_note(
            getattr(g, "dil_user", None), getattr(g, "dil_identity", None)
        ):
            return _response({"error": "CREDIT_NOTE_PREVIEW_FORBIDDEN"}, 403)

        # CSRF must follow the existing dashboard double-submit policy.
        from dashboard_sessions import csrf_valid
        if csrf_valid() is not True:
            return _response({"error": "CREDIT_NOTE_PREVIEW_CSRF_DENIED"}, 403)
        if request.headers.get("X-DIL-CN-Preview") != "1":
            return _response({"error": "EXPLICIT_PREVIEW_INTENT_REQUIRED"}, 403)

        if request.content_length is None:
            return _response({"error": "UPLOAD_LENGTH_REQUIRED"}, 411)
        if request.content_length > MAX_BYTES + 65536:
            return _response({"error": "UPLOAD_OVER_8MIB"}, 413)
        if request.mimetype != "multipart/form-data":
            return _response({"error": "MULTIPART_UPLOAD_REQUIRED"}, 415)
        request.max_content_length = MAX_BYTES + 65536

        try:
            uploads = request.files.getlist("file")
            if len(uploads) != 1 or set(request.files) != {"file"}:
                return _response({"error": "EXACTLY_ONE_FILE_REQUIRED"}, 400)
            file = uploads[0]
            filename = file.filename or ""
            if (
                not filename or len(filename) > 180
                or "/" in filename or "\\" in filename
                or any(ord(c) < 32 for c in filename)
                or not filename.lower().endswith((".csv", ".xlsx"))
            ):
                return _response({"error": "INVALID_CREDIT_NOTE_FILE_NAME"}, 400)

            data = file.stream.read(MAX_BYTES + 1)
            if not data:
                return _response({"error": "EMPTY_CREDIT_NOTE_FILE"}, 400)
            if len(data) > MAX_BYTES:
                return _response({"error": "UPLOAD_OVER_8MIB"}, 413)

            # No financial write; route returns a preliminary preview only.
            preview, errors_csv = preview_handler(filename, data)
            if not isinstance(preview, dict) or not isinstance(errors_csv, bytes):
                return _response({"error": "INVALID_PREVIEW_RESULT"}, 503)
            if (
                preview.get("import_ready") is not False
                or preview.get("database_changed") is not False
                or preview.get("release_status") != "REVIEW_REQUIRED"
            ):
                return _response({"error": "UNSAFE_PREVIEW_RESULT"}, 503)

            if request.args.get("format", "") == "errors":
                response = Response(errors_csv, mimetype="text/csv")
                response.headers["Content-Disposition"] = (
                    'attachment; filename="SBI_Credit_Note_Error_Review.csv"'
                )
                response.headers["Cache-Control"] = "private, no-store"
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                return response
            if request.args.get("format", ""):
                return _response({"error": "UNSUPPORTED_PREVIEW_FORMAT"}, 400)
            return _response(preview)
        except RequestEntityTooLarge:
            return _response({"error": "UPLOAD_OVER_8MIB"}, 413)
        except (ValueError, TypeError):
            return _response({"error": "INVALID_CREDIT_NOTE_SOURCE"}, 400)
        except Exception:
            current_app.logger.exception("Credit Note staging preview failure")
            return _response({"error": "CREDIT_NOTE_PREVIEW_UNAVAILABLE"}, 503)

    return bp
