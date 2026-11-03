"""Synthetic-only attestation tests: never use real GCP or financial data."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "staging/aws_backend_readonly/live_financial_metadata_probe.py"
SPEC = importlib.util.spec_from_file_location("metadata_probe", SOURCE)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def baseline():
    return {
        "state": "READY",
        "source_sha256": mod.SOURCE_SHA256,
        "rows": 14374,
        "unpaid_payment_state": "READY",
        "unpaid_payment_count": 2430,
        "unpaid_payment_basis": mod.APPROVED_BASIS,
        "original_columns_state": "READY",
        "original_column_count": 53,
        "original_columns_row_count": 14374,
        "original_headers": mod.approved_headers(),
    }


class SingleDocumentClient:
    def __init__(self, payload=None, *, exists=True, fault=False):
        self.payload = payload
        self.exists = exists
        self.fault = fault
        self.calls = []

    def collection(self, name):
        self.calls.append(("collection", name))
        return self

    def document(self, name):
        self.calls.append(("document", name))
        return self

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        if self.fault:
            raise RuntimeError("SENSITIVE_FAKE_AUTH_FAILURE")
        return self

    def to_dict(self):
        return self.payload


class MetadataProbeContracts(unittest.TestCase):
    def test_dry_run_does_not_open_database(self):
        client = SingleDocumentClient(baseline(), fault=True)
        report = mod.run(client=client)
        self.assertEqual(report["status"], "DRY_RUN_NO_DATABASE_ACCESS")
        self.assertEqual(client.calls, [])
        self.assertFalse(report["firestore_read_verified"])
        self.assertFalse(report["aws_backend_connected"])
        self.assertFalse(report["report_data_certified"])

    def test_single_document_get_and_no_writes(self):
        client = SingleDocumentClient(baseline())
        report = mod.run(client=client, live_read=True)
        self.assertEqual(report["status"], "PASS_METADATA_ONLY")
        self.assertTrue(report["firestore_read_verified"])
        self.assertEqual(client.calls, [
            ("collection", "dashboard_report_datasets"),
            ("document", mod.DATASET),
            ("get", {"timeout": 10, "retry": None}),
        ])
        self.assertFalse(report["aws_backend_connected"])
        self.assertFalse(report["report_data_certified"])
        self.assertFalse(report["financial_execution_enabled"])
        self.assertEqual(report["financial_writes_performed"], 0)
        self.assertNotIn("original_headers", report)

    def test_every_source_guard_is_fail_closed(self):
        changes = {
            "state": "PENDING",
            "source_sha256": "0" * 64,
            "rows": 1,
            "unpaid_payment_state": "PENDING",
            "unpaid_payment_count": 1,
            "unpaid_payment_basis": "UNAPPROVED",
            "original_columns_state": "PENDING",
            "original_column_count": 34,
            "original_columns_row_count": 1,
            "original_headers": list(reversed(mod.approved_headers())),
        }
        for key, broken in changes.items():
            with self.subTest(key=key):
                sample = baseline()
                sample[key] = broken
                result = mod.run(live_read=True, client=SingleDocumentClient(sample))
                self.assertEqual(result["status"], "BLOCKED")
                self.assertFalse(result["firestore_read_verified"])
                self.assertTrue(result["blockers"])

    def test_header_order_and_duplicates_are_preserved(self):
        headers = mod.approved_headers()
        self.assertEqual(len(headers), 53)
        self.assertGreater(len(headers), len(set(headers)))
        self.assertEqual(mod.header_fingerprint(headers),
                         mod.header_fingerprint(list(headers)))
        self.assertNotEqual(mod.header_fingerprint(headers),
                            mod.header_fingerprint(list(reversed(headers))))
        original = json.loads(
            (ROOT / "backend_source/invoice_import_contract.json").read_text()
        )["headers"]
        self.assertEqual(headers, original)

    def test_missing_document_fails_closed(self):
        report = mod.run(live_read=True, client=SingleDocumentClient(exists=False))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("DATASET_METADATA_MISSING", report["blockers"])

    def test_credentials_and_errors_never_leak(self):
        client = SingleDocumentClient(baseline(), fault=True)
        report = mod.run(live_read=True, client=client)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertNotIn("SENSITIVE_FAKE_AUTH_FAILURE", json.dumps(report))
        self.assertIn("FIRESTORE_AUTH_OR_CONNECTIVITY_FAILED", report["blockers"])
        self.assertEqual(report["financial_writes_performed"], 0)

    def test_invalid_header_contract_fails_without_read(self):
        client = SingleDocumentClient(baseline())
        report = mod.run(live_read=True, client=client,
                         contract_path=ROOT / "nonexistent.json")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(client.calls, [])

    def test_no_writer_operations_or_aws_image_changes(self):
        content = SOURCE.read_text()
        for name in (".set(", ".update(", ".delete(", ".batch(", ".commit(",
                     "subprocess", "firebase_admin", "upload", "payment_allocation"):
            self.assertNotIn(name, content)
        image = (ROOT / "staging/aws_backend_readonly/Dockerfile").read_text()
        compose = (ROOT / "staging/aws_backend_readonly/compose.yaml").read_text()
        self.assertNotIn("live_financial_metadata_probe.py", image)
        self.assertIn("internal: true", compose)


if __name__ == "__main__":
    unittest.main()
