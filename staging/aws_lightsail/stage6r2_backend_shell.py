#!/usr/bin/env python3
"""Stage 6R.2 inert backend recovery shell, NOT the financial service.

Runs only in an isolated, network-none Docker container. It deliberately never
imports original backend modules, obtains credentials or connects to a database.
All original financial/import/admin/report routes return HTTP 503.
"""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys

SOURCE = Path("/opt/sbi-backend-source")
REQUIRED = ("main.py", "report_api.py", "payment_report_rules.py",
            "credit_note_report.py", "invoice_import_contract.json",
            "invoice_source_schema.py", "sbi_firestore_contract_v5.py")

def gate(env=None, source=SOURCE):
    env = os.environ if env is None else env
    if env.get("SBI_RECOVERY_PROFILE") != "lightsail-isolated-no-finance":
        return "BLOCKED_PROFILE"
    if env.get("SBI_FINANCIAL_EXECUTION") != "disabled":
        return "BLOCKED_FINANCIAL_EXECUTION"
    if env.get("SBI_BACKEND_CONNECTED") != "false":
        return "BLOCKED_BACKEND_CONNECTED"
    if not all((source / name).is_file() for name in REQUIRED):
        return "BLOCKED_SOURCE_MODULES"
    return "READY_INERT_BACKEND_PACKAGE"

class SafeHandler(BaseHTTPRequestHandler):
    server_version = "SBI-Recovery-Shell"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Do not log request paths or tokens.
        return

    def reply(self, status, payload):
        body=json.dumps(payload,separators=(",",":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self.reply(200,{
                "stage":"6R.2",
                "source_package":"RECOVERED",
                "financial_execution":False,
                "backend_connected":False,
                "real_firebase_auth":"NOT_TESTED",
                "live_database":"NOT_CONNECTED",
                "release":"PRIVATE_PACKAGE_ONLY"
            })
        self.reply(503,{"error":"Financial/backend API disabled for private recovery package"})

    def do_POST(self):
        self.reply(503,{"error":"Financial/backend API disabled for private recovery package"})

    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST

def main():
    status=gate()
    print("STAGE6R2_PACKAGE_GATE="+status,flush=True)
    if status != "READY_INERT_BACKEND_PACKAGE":
        return 78
    if "--check" in sys.argv:
        print("FINANCIAL_EXECUTION=DISABLED",flush=True)
        print("LIVE_DATABASE=NOT_CONNECTED",flush=True)
        return 0
    # Only the container's own loopback; host must never publish this container.
    host=ThreadingHTTPServer(("127.0.0.1",8081),SafeHandler)
    host.serve_forever(poll_interval=0.2)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
