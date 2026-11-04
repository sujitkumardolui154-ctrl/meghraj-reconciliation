"""Stage 6C AWS private staging guard: fail closed for all backend routes."""
from flask import jsonify, request
from stage6_origin_policy import aws_private_mode, private_aws_origin

def install_aws_private_guard(app):
    if app.extensions.get("stage6_aws_guard"):
        raise RuntimeError("Stage 6 guard already installed")
    app.extensions["stage6_aws_guard"] = True

    @app.before_request
    def stage6_backend_gate():
        if not aws_private_mode():
            return None
        if private_aws_origin() is None:
            return jsonify(error="AWS origin not configured"), 503
        if (request.path.startswith("/api/") or
                request.path.startswith("/reports/") or
                request.path in ("/api", "/reports")):
            return jsonify(error="Stage 6 AWS backend integration disabled"), 503
        return None
