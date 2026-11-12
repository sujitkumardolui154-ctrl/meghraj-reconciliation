#!/usr/bin/env python3
"""One-run, fail-closed SBI CN remaining QA (WS-LOCK-001).

Runs ALL locally executable offline suites and a temporary loopback-only
HTTP smoke test, then reports the *independently unverified* release gates.
Never reads a financial database, validates IAM by inference, or deploys.
No production traffic, Firebase sessions, credentials or financial writes.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SUITES = (
    ("CREDIT_NOTE_VALIDATION", "test_credit_note_import_preview_v2.py"),
    ("INVOICE_IMPORT_COMPATIBILITY", "test_credit_note_invoice_preview_bridge.py"),
    ("REGISTRY_AND_FILE_PREVIEW", "test_credit_note_registry_preview.py"),
    ("HTTP_AUTH_AND_INDEX_PREFLIGHT", "test_credit_note_staging_http_and_index_audit.py"),
    ("ISOLATED_REAL_MIDDLEWARE_SYNTHETIC", "test_sbi_cn_isolated_app_e2e.py"),
)
SOURCE_FILES = (
    "backend_source/credit_note_validation.py",
    "backend_source/credit_note_import_preview.py",
    "backend_source/credit_note_registry_readonly.py",
    "backend_source/credit_note_registry_audit.py",
    "backend_source/credit_note_import_file.py",
    "backend_source/invoice_import_preview.py",
    "dashboard_source/sbi_cn_staging_preview.py",
    "staging/sbi_cn_isolated_stage_app.py",
    "dashboard_source/dashboard_sessions.py",
)
EXTERNAL_GATES = {
    "REAL_FIREBASE_LOGIN_AND_REVOKED_COOKIE": "NOT_TESTED",
    "PRIVATE_HTTPS_STAGING_ORIGIN": "NOT_VERIFIED",
    "EFFECTIVE_READONLY_CLOUD_IAM": "NOT_VERIFIED",
    "LIVE_FINANCIAL_DATABASE_CONNECTION": "NOT_ATTEMPTED",
    "HISTORICAL_INVOICE_CN_INDEX_BACKFILL_PARITY": "NOT_VERIFIED",
    "HISTORICAL_DUPLICATE_CN_CONFLICT_RESOLUTION": "PENDING_REVIEW",
    "PAYMENT_IMPORT_AND_FINANCIAL_VALUE_PARITY": "NOT_TESTED",
    "INDEPENDENT_BACKUP_AND_ROLLBACK_EVIDENCE": "NOT_VERIFIED",
    "PRODUCTION_OWNER_AUTHORIZATION": "NOT_GRANTED",
}


def git_rev():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip() if result.returncode == 0 else "UNKNOWN"


def source_safety():
    try:
        for path in SOURCE_FILES:
            filename = ROOT / path
            ast.parse(filename.read_text(encoding="utf-8"), filename=path)
        gateway = (ROOT / "dashboard_source/production_gateway.py").read_text(
            encoding="utf-8"
        )
        stage = (ROOT / "staging/sbi_cn_isolated_stage_app.py").read_text(
            encoding="utf-8"
        )
        return (
            "create_credit_note_staging_blueprint" not in gateway
            and "sbi_cn_isolated_stage_app" not in gateway
            and "offline_preview" in stage
            and "install_sessions(app)" in stage
            and "register_blueprint" in stage
        )
    except (OSError, SyntaxError, UnicodeError):
        return False


def test_suites(python_bin):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT), str(ROOT / "dashboard_source"),
         str(ROOT / "backend_source"), env.get("PYTHONPATH", "")]
    )
    result = {}
    total = 0
    all_ok = True
    for label, pattern in SUITES:
        try:
            run = subprocess.run(
                [python_bin, "-B", "-m", "unittest", "discover",
                 "-s", str(ROOT / "tests"), "-p", pattern, "-v"],
                cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=120,
            )
            output = (run.stdout + "\n" + run.stderr)
            count = re.findall(r"Ran (\d+) tests?", output)
            passed = run.returncode == 0 and bool(count)
            quantity = int(count[-1]) if count else 0
            total += quantity
            all_ok &= passed
            result[label] = {
                "status": "PASS" if passed else "FAIL",
                "tests_run": quantity,
                "exit_code": run.returncode,
            }
            print(f"{label}={'PASS' if passed else 'FAIL'} TESTS={quantity}", flush=True)
            if not passed:
                # Avoid printing proprietary financial records or credentials.
                print(f"{label}_DETAILS=SEE_LOCAL_TEST_LOGS", flush=True)
        except (OSError, subprocess.TimeoutExpired):
            all_ok = False
            result[label] = {"status": "FAIL", "tests_run": 0}
            print(f"{label}=FAIL TESTS=0", flush=True)
    return result, total, all_ok


def get_http_code(port, path, method, origin=None):
    headers = {"Origin": origin} if origin else {}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        headers=headers,
        data=b"" if method == "POST" else None
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def smoke_loopback(python_bin):
    # Never contact a public origin. Start a short-lived loopback-only process.
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "SBI_CN_ISOLATED_STAGE": "1",
            "SBI_CN_STAGING_PREVIEW_ENABLED": "true",
        }
        process = subprocess.Popen(
            [python_bin, "-B", "-m", "gunicorn",
             "staging.sbi_cn_isolated_stage_app:create_app()",
             "--bind", f"127.0.0.1:{port}",
             "--workers", "1", "--timeout", "20"],
            cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return {"status": "FAIL", "reason": "LOOPBACK_PROCESS_NOT_STARTED"}

    result = {"status": "FAIL", "health": None,
              "anonymous_preview": None, "untrusted_origin": None}
    try:
        for _ in range(40):
            if process.poll() is not None:
                break
            try:
                if get_http_code(port, "/healthz", "GET") == 401:
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(.2)
        if process.poll() is not None:
            result["reason"] = "STAGING_PROCESS_EARLY_EXIT"
            return result
        trusted_origin = "https://sbi-dashboard-ahz6wqeiaq-el.a.run.app"
        result["health"] = get_http_code(port, "/healthz", "GET")
        result["anonymous_preview"] = get_http_code(
            port, "/staging/credit-note/import-preview", "POST",
            trusted_origin
        )
        result["untrusted_origin"] = get_http_code(
            port, "/staging/credit-note/import-preview", "POST",
            "https://untrusted.example.invalid"
        )
        result["status"] = (
            "PASS" if (result["health"], result["anonymous_preview"],
                       result["untrusted_origin"]) == (401, 401, 403)
            else "FAIL"
        )
        return result
    except (OSError, TimeoutError):
        result["reason"] = "LOCAL_HTTP_REQUEST_FAILED"
        return result
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait()
        result["temporary_server"] = "STOPPED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="Optional separate QA-only JSON path")
    args = parser.parse_args()
    print("=== SBI CREDIT NOTE ONE-RUN COMBINED REMAINING QA ===", flush=True)
    print("SOURCE_COMMIT=" + git_rev(), flush=True)

    source_ok = source_safety()
    print("SOURCE_AND_PRODUCTION_ISOLATION=" +
          ("PASS" if source_ok else "FAIL"), flush=True)
    groups, count, suites_ok = test_suites(sys.executable)
    smoke = smoke_loopback(sys.executable)
    print("LOOPBACK_HTTP_QA=" + smoke["status"], flush=True)
    print("ANONYMOUS_HEALTH_HTTP=" + str(smoke.get("health")), flush=True)
    print("ANONYMOUS_PREVIEW_HTTP=" + str(smoke.get("anonymous_preview")), flush=True)
    print("UNTRUSTED_ORIGIN_HTTP=" + str(smoke.get("untrusted_origin")), flush=True)
    print("TEMPORARY_SERVER=" + str(smoke.get("temporary_server", "NOT_STARTED")),
          flush=True)
    testable_pass = source_ok and suites_ok and smoke["status"] == "PASS"

    report = {
        "title": "SBI CN combined remaining QA",
        "source_commit": git_rev(),
        "testable_local_qa": "PASS" if testable_pass else "FAIL",
        "total_unit_tests": count,
        "unit_test_groups": groups,
        "source_isolation": "PASS" if source_ok else "FAIL",
        "loopback_smoke": smoke,
        "external_gates": EXTERNAL_GATES,
        "live_financial_database_access": "NOT_ATTEMPTED",
        "real_firebase_login": "NOT_TESTED",
        "effective_iam": "NOT_VERIFIED",
        "financial_database_writes": "NOT_PERFORMED_BY_QA",
        "deployment": "NOT_PERFORMED_BY_QA",
        "production_cutover": "BLOCKED",
        "combined_result": (
            "COMPLETE_WITH_EXTERNAL_BLOCKERS"
            if testable_pass else "LOCAL_QA_FAILED_RELEASE_BLOCKED"
        ),
    }
    if args.report:
        out = Path(args.report).resolve()
        if out.suffix.lower() != ".json" or out.is_dir():
            parser.error("Report output must end in .json")
        # Explicitly provided QA-only report; never replace source evidence.
        if out.exists():
            parser.error("Refusing to overwrite existing report")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("QA_REPORT_PATH=" + str(out), flush=True)

    print("=== EXTERNAL RELEASE GATES ===", flush=True)
    for name, status in EXTERNAL_GATES.items():
        print(f"{name}={status}", flush=True)
    print(f"OFFLINE_TESTS={count}", flush=True)
    print("FINANCIAL_WRITES=NOT_PERFORMED_BY_QA", flush=True)
    print("PRODUCTION_CUTOVER=BLOCKED", flush=True)
    print("SBI_COMBINED_REMAINING_QA=" + report["combined_result"], flush=True)
    return 0 if testable_pass else 1


if __name__ == "__main__":
    sys.exit(main())
