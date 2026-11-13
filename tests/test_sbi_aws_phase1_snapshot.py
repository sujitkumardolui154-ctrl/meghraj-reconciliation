"""Offline contract tests for immutable AWS Phase 1 private report serving.

Synthetic 53-/18-column CSVs only. No financial records, cloud connections,
host credentials, server deployment, or actual financial database access.
"""
import base64
import csv
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend_source"
sys.path.insert(0, str(BACKEND))
spec = importlib.util.spec_from_file_location(
    "aws_phase1_snapshot_test_gateway",
    BACKEND / "aws_readonly_reporting_app.py",
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

USERNAME = "offline-synthetic"
PASSWORD = "offline-qa-password-not-a-real-secret"
BASIC = "Basic " + base64.b64encode(
    (USERNAME + ":" + PASSWORD).encode()
).decode()


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def header_pin(headers):
    return checksum(json.dumps(
        headers, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8"))


class AWSPhase1SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.headers53 = ["Source Field " + str(i + 1) for i in range(53)]
        self.headers18 = ["CN Field " + str(i + 1) for i in range(18)]
        self.environment = {
            "SBI_SOURCE_SHA": "b" * 40,
            "SBI_AWS_REPORT_USERNAME": USERNAME,
            "SBI_AWS_REPORT_PASSWORD": PASSWORD,
            "SBI_AWS_REPORT_SNAPSHOT_DIR": str(self.dir),
            "SBI_AWS_APPROVED_53_HEADERS_SHA256": header_pin(self.headers53),
            "SBI_AWS_APPROVED_18_HEADERS_SHA256": header_pin(self.headers18),
        }
        now = dt.datetime.now(dt.timezone.utc)
        self.manifest = {
            "schema": "sbi-aws-phase1-private-snapshot/v1",
            "release_class": "REPORTING_ONLY",
            "approval_status": "INDEPENDENTLY_APPROVED",
            "approval_receipt_id": "OFFLINE-SYNTHETIC-01",
            "financial_writes_disabled": True,
            "reconciliation_executed": False,
            "source_sha256": "c" * 64,
            "approved_at_utc": (now - dt.timedelta(minutes=5)).isoformat(),
            "expires_at_utc": (now + dt.timedelta(hours=1)).isoformat(),
            "reports": {},
            "credit_note_conflicts_resolved": False,
        }
        for kind in ("unpaid", "ok", "balance-review"):
            self.add_report(kind, self.headers53)
        self.repin()
        gateway.app.testing = True
        self.client = gateway.app.test_client()

    def add_report(self, kind, headers, *, value="SYNTHETIC_TEST"):
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerow([value] * len(headers))
        raw = stream.getvalue().encode("utf-8")
        (self.dir / (kind + ".csv")).write_bytes(raw)
        self.manifest["reports"][kind] = {
            "file": kind + ".csv",
            "sha256": checksum(raw),
            "row_count": 1,
            "column_count": len(headers),
            "headers": headers,
            "classification": "SOURCE_REFERENCE_ONLY",
        }

    def repin(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode("utf-8")
        (self.dir / "manifest.json").write_bytes(raw)
        self.environment["SBI_AWS_REPORT_MANIFEST_SHA256"] = checksum(raw)

    def response(self, route, *, authorized=True, env=None, method="GET"):
        with patch.dict(os.environ, env if env is not None else self.environment, clear=True):
            headers = {"Authorization": BASIC} if authorized else {}
            return self.client.open(route, method=method, headers=headers)

    def test_core_readiness_and_report_data_are_real_synthetic_bytes(self):
        ready = self.response("/readyz", authorized=False)
        self.assertEqual(ready.status_code, 200)
        self.assertFalse(ready.json["financial_execution_enabled"])
        catalog = self.response("/reports")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(set(catalog.json["reports"]), {"unpaid", "ok", "balance-review"})
        self.assertFalse(catalog.json["reconciliation_executed"])
        report = self.response("/reports/ok.csv")
        self.assertEqual(report.status_code, 200)
        self.assertIn(b"SYNTHETIC_TEST", report.data)
        self.assertEqual(report.headers["X-Report-Classification"], "SOURCE_REFERENCE_ONLY")

    def test_missing_snapshot_is_original_fail_closed_503(self):
        self.assertEqual(self.response("/readyz", env={}).status_code, 503)
        self.assertEqual(self.response("/reports", env={}).status_code, 503)

    def test_authorization_required_even_with_approved_files(self):
        self.assertEqual(self.response("/reports", authorized=False).status_code, 401)
        self.assertEqual(self.response("/reports/ok.csv", authorized=False).status_code, 401)

    def test_manifest_hash_mismatch_blocks_all(self):
        env = {**self.environment, "SBI_AWS_REPORT_MANIFEST_SHA256": "0" * 64}
        self.assertEqual(
            self.response("/reports", env=env).json["error"],
            "SNAPSHOT_MANIFEST_HASH_MISMATCH",
        )

    def test_report_tampering_blocks_without_exposing_value(self):
        (self.dir / "ok.csv").write_bytes(b"PRIVATE_TAMPERED")
        result = self.response("/reports/ok.csv")
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b"PRIVATE_TAMPERED", result.data)

    def test_independent_53_headers_pin_required(self):
        env = self.environment.copy()
        env.pop("SBI_AWS_APPROVED_53_HEADERS_SHA256")
        result = self.response("/reports", env=env)
        self.assertEqual(result.status_code, 503)
        self.assertEqual(
            result.json["error"], "INDEPENDENT_HEADER_CONTRACT_NOT_VERIFIED"
        )

    def test_expired_approval_is_not_served(self):
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        self.manifest["expires_at_utc"] = past.isoformat()
        self.repin()
        self.assertEqual(self.response("/reports").status_code, 503)

    def test_unapproved_credit_note_export_is_denied(self):
        self.add_report("credit-note", self.headers18)
        self.repin()
        result = self.response("/reports/credit-note.csv")
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json["error"], "CREDIT_NOTE_CONFLICTS_PENDING_REVIEW")
        # Reporting index omits unresolved Credit Notes.
        catalog = self.response("/reports")
        self.assertEqual(catalog.status_code, 200)
        self.assertNotIn("credit-note", catalog.json["reports"])

    def test_unapproved_manifest_status_blocks(self):
        self.manifest["approval_status"] = "PENDING_REVIEW"
        self.repin()
        self.assertEqual(self.response("/reports/ok.csv").status_code, 503)

    def test_csv_formula_injection_rejected(self):
        self.add_report("ok", self.headers53, value="=HYPERLINK('x')")
        self.repin()
        r = self.response("/reports/ok.csv")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json["error"], "SNAPSHOT_CSV_FORMULA_NOT_ESCAPED")

    def test_manifest_path_traversal_rejected(self):
        self.manifest["reports"]["ok"]["file"] = "../other.csv"
        self.repin()
        self.assertEqual(self.response("/reports/ok.csv").status_code, 503)

    def test_symlink_csv_is_not_followed(self):
        source = self.dir / "ok.csv"
        other = self.dir / "original.csv"
        source.rename(other)
        source.symlink_to(other)
        self.assertEqual(self.response("/reports/ok.csv").status_code, 503)

    def test_write_methods_never_enabled(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(
                    self.response("/reports", method=method).status_code, 403
                )

    def test_gateway_has_no_finance_writer_imports(self):
        app = (BACKEND / "aws_readonly_reporting_app.py").read_text()
        adapter = (BACKEND / "aws_readonly_snapshot_reports.py").read_text()
        dockerfile = (ROOT / "staging/aws_phase1_reporting/Dockerfile").read_text()
        for content in (app, adapter, dockerfile):
            for banned in ("firebase_admin", "google.cloud.firestore",
                           "payment_allocation", "set_custom_user_claims"):
                self.assertNotIn(banned, content)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertNotIn("COPY backend_source/ /app", dockerfile)


if __name__ == "__main__":
    unittest.main()
