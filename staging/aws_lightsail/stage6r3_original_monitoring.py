#!/usr/bin/env python3
"""Stage 6R.3: run only original safe monitoring routes from recovered main.py.

This is an isolated, localhost-only, no-finance compatibility test, NOT the
production backend. No financial modules imported, database, IAM or network.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType, SimpleNamespace

SOURCE = Path("/opt/sbi-backend-source/main.py")
SAFE = frozenset({"/health", "/qa", "/supervisor", "/agents"})
EXPECTED = {
    "/health": {"service", "project", "status", "financial_execution_enabled", "timestamp_utc"},
    "/qa": {"data_source", "qa_status", "production_release", "issues"},
    "/supervisor": {"supervisor", "monitoring_mode", "production_release",
                    "financial_engine", "financial_execution_enabled", "timestamp_utc"},
    "/agents": {"data_source", "live_agent_connection", "agents"},
}
MISSING = object()

def gate(env=None, path=SOURCE):
    env = os.environ if env is None else env
    if env.get("SBI_RECOVERY_PROFILE") != "lightsail-original-readonly-monitoring":
        return "BLOCKED_PROFILE"
    if env.get("SBI_FINANCIAL_EXECUTION") != "disabled":
        return "BLOCKED_FINANCE"
    if env.get("SBI_BACKEND_CONNECTED") != "false":
        return "BLOCKED_BACKEND"
    if env.get("SBI_SOURCE_REVISION_PARITY") != "unverified":
        return "BLOCKED_PARITY"
    if any(env.get(k) for k in (
        "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_API_CERTIFICATE_CONFIG",
        "REPORT_BACKEND", "IMPORT_BACKEND", "DATABASE_URL"
    )):
        return "BLOCKED_CLOUD_CREDENTIALS_OR_BACKEND"
    if not path.is_file():
        return "BLOCKED_SOURCE"
    return "READY_PRIVATE_ORIGINAL_MONITOR_ONLY"

def load_original(path=SOURCE):
    """Import pinned original main.py with only its HTTP decorator shimmed.

    The trusted source must come from an exact Git commit copied into the
    offline image. Real functions-framework is not installed in the base.
    """
    shim = ModuleType("functions_framework")
    shim.http = lambda fn: fn
    previous = sys.modules.get("functions_framework", MISSING)
    sys.modules["functions_framework"] = shim
    try:
        spec = importlib.util.spec_from_file_location("_sbi_stage6r3_original_main", str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Missing original backend source loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = module.supervisor_api
        if not callable(handler):
            raise RuntimeError("Original backend handler unavailable")
        return handler
    finally:
        if previous is MISSING:
            sys.modules.pop("functions_framework", None)
        else:
            sys.modules["functions_framework"] = previous

def allowed_payload(route, payload):
    if not isinstance(payload, dict) or set(payload) != EXPECTED.get(route, set()):
        return False
    if route == "/health":
        return (payload["project"] == "meghraj-reconciliation"
                and payload["service"] == "sbi-supervisor-backend"
                and payload["financial_execution_enabled"] is False)
    if route == "/qa":
        return (payload["data_source"] == "STATIC_BASELINE"
                and payload["production_release"] == "BLOCKED"
                and payload["qa_status"] == "PENDING")
    if route == "/supervisor":
        return (payload["monitoring_mode"] == "STATIC_BASELINE"
                and payload["production_release"] == "BLOCKED"
                and payload["financial_engine"] == "NOT_DEPLOYED"
                and payload["financial_execution_enabled"] is False)
    if route == "/agents":
        return (payload["data_source"] == "DEMONSTRATION_ONLY"
                and payload["live_agent_connection"] is False)
    return False

class Handler(BaseHTTPRequestHandler):
    server_version = "SBI-Private-Source-Monitor"
    sys_version = ""

    def log_message(self, fmt, *args):
        return  # No potentially sensitive request paths or headers in logs.

    def send_json(self, status, obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/healthz":
            return self.send_json(200, {
                "stage": "6R.3", "source_monitoring": "ORIGINAL_MAIN_PY_STATIC",
                "firebase_real_login": "NOT_TESTED",
                "financial_database": "NOT_CONNECTED",
                "financial_execution": False,
                "release": "PRIVATE_MONITORING_ONLY"
            })
        if self.path not in SAFE:
            return self.send_json(503, {"error": "Backend or financial route disabled"})
        try:
            body, status, headers = self.server.original(SimpleNamespace(path=self.path, method="GET"))
            payload = json.loads(body)
            if status != 200 or not allowed_payload(self.path, payload):
                raise ValueError("Untrusted original monitoring source response")
        except Exception:
            return self.send_json(503, {"error": "Monitoring source contract unavailable"})
        self.send_json(200, payload)

    def do_POST(self):
        self.send_json(503, {"error": "Mutation and backend API disabled"})
    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

def main():
    result = gate()
    print("STAGE6R3_GATE=" + result, flush=True)
    if result != "READY_PRIVATE_ORIGINAL_MONITOR_ONLY":
        return 78
    try:
        original = load_original()
        for route in sorted(SAFE):
            body, status, _ = original(SimpleNamespace(path=route, method="GET"))
            if status != 200 or not allowed_payload(route, json.loads(body)):
                print("ORIGINAL_MONITORING_CONTRACT=BLOCKED", flush=True)
                return 78
    except Exception:
        print("ORIGINAL_MONITORING_CONTRACT=BLOCKED", flush=True)
        return 78
    print("ORIGINAL_MONITORING_CONTRACT=PASS", flush=True)
    print("FINANCIAL_DATABASE=NOT_CONNECTED", flush=True)
    if "--check" in sys.argv:
        return 0
    server = ThreadingHTTPServer(("127.0.0.1", 8082), Handler)
    server.original = original
    server.serve_forever(poll_interval=0.2)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
