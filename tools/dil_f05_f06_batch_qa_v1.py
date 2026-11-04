#!/usr/bin/env python3
"""F05/F06 consolidated offline QA. Never opens network or financial data."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKS = {}

def record(name, passed, detail=""):
    CHECKS[name] = {"status": "PASS" if passed else "FAIL", "detail": detail}

def main():
    targets = [
        ROOT / "dashboard_source/dil_invoice_intelligence_pipeline.py",
        ROOT / "dashboard_source/dil_authorized_invoice_adapter.py",
        ROOT / "tests/test_dil_invoice_intelligence_pipeline.py",
        ROOT / "tests/test_dil_authorized_invoice_adapter.py",
    ]
    for path in targets:
        try:
            compile(path.read_bytes(), str(path), "exec")
            record("syntax:" + path.name, True)
        except Exception as exc:
            record("syntax:" + path.name, False, type(exc).__name__)
    if all(v["status"] == "PASS" for v in CHECKS.values()):
        sys.path.insert(0, str(ROOT))
        suite = unittest.TestLoader().loadTestsFromNames([
            "tests.test_dil_invoice_intelligence_pipeline",
            "tests.test_dil_authorized_invoice_adapter",
        ])
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        record("synthetic_auth_and_no_write", result.wasSuccessful(),
               f"ran={result.testsRun} errors={len(result.errors)} failures={len(result.failures)}")
    else:
        CHECKS["synthetic_auth_and_no_write"] = {"status": "BLOCKED", "detail": "syntax failed"}
    for name in ("real_firebase_login", "live_financial_parity", "production_cutover"):
        CHECKS[name] = {"status": "BLOCKED", "detail": "requires independent approval; not attempted"}
    failed = any(v["status"] == "FAIL" for v in CHECKS.values())
    print(json.dumps({"version": "F05-F06-BATCH-QA-v1", "checks": CHECKS,
                      "BATCH_QA": "FAIL" if failed else "PASS_OFFLINE_ONLY",
                      "NEXT_GATE": "INDEPENDENT_REVIEW_AND_APPROVED_PRIVATE_STAGING"},
                     indent=2))
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
