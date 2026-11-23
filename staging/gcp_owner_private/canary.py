"""Minimal IAM-fronted Cloud Run staging canary.

This is deliberately NOT the financial dashboard or reconciliation backend.
It demonstrates the release's source identity and fail-closed HTTP behavior.
No cloud SDK, financial data, external HTTP client, or database dependencies.
Cloud Run IAM MUST be used; the HTTP server is not an authentication layer.
"""
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SOURCE_DIR = Path("/opt/sbi/source")
SOURCE_MANIFEST = SOURCE_DIR / "RELEASE_PREFLIGHT_MANIFEST.json"
BLOCKED_ROUTES = ("/api/", "/imports", "/upload", "/reports", "/payments",
                  "/reconciliation", "/admin", "/credit-note", "/firebase")
EXPECTED_FLAGS = {
    "STAGING_ONLY": "true",
    "FINANCIAL_WRITES_DISABLED": "true",
    "RECONCILIATION_EXECUTION_ENABLED": "false",
}


def validate_runtime(environ=None, source_manifest=SOURCE_MANIFEST):
    environ = environ if environ is not None else os.environ
    if any(environ.get(k) != v for k, v in EXPECTED_FLAGS.items()):
        raise RuntimeError("BLOCKED_STAGING_RUNTIME_FLAGS")
    commit = environ.get("SOURCE_COMMIT_SHA", "")
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise RuntimeError("BLOCKED_UNPINNED_SOURCE_COMMIT")
    manifest = json.loads(Path(source_manifest).read_text(encoding="utf-8"))
    if manifest.get("result") != "PASS_SOURCE_PACKAGE_ONLY":
        raise RuntimeError("BLOCKED_UNVERIFIED_SOURCE_PACKAGE")
    if manifest.get("production_release") != "BLOCKED":
        raise RuntimeError("BLOCKED_RELEASE_GUARD_MISSING")
    if manifest.get("finance_database_write_permission") != "NOT_GRANTED":
        raise RuntimeError("BLOCKED_FINANCE_PERMISSION")
    if manifest.get("cloud_staging_deployment") != "NOT_PERFORMED":
        raise RuntimeError("BLOCKED_SOURCE_PROOF_FALSE_CLAIM")
    records = manifest.get("source_files")
    if not isinstance(records, dict) or len(records) != 8:
        raise RuntimeError("BLOCKED_INCOMPLETE_SOURCE_PROOF")
    root = Path(source_manifest).parent.resolve()
    for rel, record in records.items():
        path = root / rel
        if not isinstance(rel, str) or not isinstance(record, dict):
            raise RuntimeError("BLOCKED_BAD_MANIFEST")
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeError("BLOCKED_UNSAFE_SOURCE_PATH")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
            raise RuntimeError("BLOCKED_SOURCE_DIGEST_MISMATCH")
    return {"source_commit": commit, "source_files_verified": len(records)}


def payload(path, verified):
    """Return (status, JSON payload). All possible finance routes denied."""
    if path == "/healthz":
        return 200, {
            "service": "sbi-owner-staging-canary",
            "mode": "READ_ONLY_SOURCE_PROOF",
            "financial_database_connected": False,
            "financial_writes_enabled": False,
            "production_release": "BLOCKED",
            "source_commit": verified["source_commit"],
        }
    if path == "/release-evidence":
        return 200, {
            "source_commit": verified["source_commit"],
            "source_files_verified": verified["source_files_verified"],
            "deployment_type": "STAGING_CANARY_ONLY",
            "finance_execution": "DISABLED",
            "real_application_runtime": "NOT_INCLUDED",
            "live_bank_invoice_parity": "NOT_VERIFIED",
            "credit_note_value_parity": "NOT_VERIFIED",
            "production_release": "BLOCKED",
        }
    if path in ("/", "/robots.txt") or path.startswith(BLOCKED_ROUTES):
        return 503, {"error": "FINANCIAL_APPLICATION_DISABLED_STAGING_ONLY",
                     "financial_writes_enabled": False}
    return 404, {"error": "NOT_FOUND"}


class Handler(BaseHTTPRequestHandler):
    verified = None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        status, body = payload(path, self.verified)
        response = (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_POST(self):
        self._deny()

    def do_PUT(self):
        self._deny()

    def do_PATCH(self):
        self._deny()

    def do_DELETE(self):
        self._deny()

    def _deny(self):
        response = b'{"error":"STAGING_READ_ONLY"}\n'
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    verified = validate_runtime()
    Handler.verified = verified
    port = int(os.environ.get("PORT", "8080"))
    if port < 1024 or port > 65535:
        raise RuntimeError("BLOCKED_INVALID_LISTEN_PORT")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
