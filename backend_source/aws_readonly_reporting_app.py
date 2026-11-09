"""Isolated AWS report-preview gateway: no imports of financial writer code."""
import hmac
import os
import re
from flask import Flask, jsonify, request

app = Flask(__name__)
REPORTS = frozenset(("unpaid", "ok", "balance-review", "suspense",
                     "credit-note", "reconciliation-changes"))
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def fail(code, status):
    return jsonify(status="REVIEW_REQUIRED", error=code,
                   financial_execution_enabled=False), status


@app.before_request
def deny_unapproved():
    if request.method != "GET":
        return fail("METHOD_DISABLED", 403)
    if request.path not in ("/healthz", "/readyz", "/reports") and not request.path.startswith("/reports/"):
        return fail("ROUTE_DISABLED", 403)


@app.after_request
def protect(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def authorized_or_error():
    user = os.environ.get("SBI_AWS_REPORT_USERNAME", "")
    password = os.environ.get("SBI_AWS_REPORT_PASSWORD", "")
    if not user or len(password) < 24:
        return fail("REPORT_AUTH_NOT_CONFIGURED", 503)
    auth = request.authorization
    valid = (auth is not None and str(auth.type).casefold() == "basic"
             and hmac.compare_digest(auth.username or "", user)
             and hmac.compare_digest(auth.password or "", password))
    if not valid:
        reply, status = fail("AUTH_REQUIRED", 401)
        reply.headers["WWW-Authenticate"] = 'Basic realm="SBI isolated AWS reports"'
        return reply, status
    return None


@app.get("/healthz")
def healthz():
    sha = os.environ.get("SBI_SOURCE_SHA", "")
    return jsonify(status="ok", service="sbi-aws-readonly-report-preview",
                   version=("git-" + sha[:12]) if SHA_RE.fullmatch(sha) else "UNVERIFIED",
                   monitoring_mode="read_only", financial_data_connected=False,
                   financial_execution_enabled=False)


@app.get("/readyz")
def readyz():
    return fail("REPORT_DATA_NOT_CERTIFIED", 503)


@app.get("/reports")
def reports():
    denied = authorized_or_error()
    return denied if denied is not None else fail("REPORT_DATA_NOT_CONNECTED", 503)


@app.get("/reports/<report_name>.csv")
def report_csv(report_name):
    denied = authorized_or_error()
    if denied is not None:
        return denied
    if report_name not in REPORTS:
        return fail("REPORT_NOT_APPROVED", 404)
    return fail("REPORT_DATA_NOT_CONNECTED", 503)


if __name__ == "__main__":
    raise SystemExit("Run via the reviewed non-root Gunicorn container")
