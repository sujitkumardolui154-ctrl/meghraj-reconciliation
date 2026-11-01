"""Synthetic-only tests: no Google credentials, network, Firestore, or deployments."""
import datetime as dt
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from sbi_reporting_production_gate import REQUIRED_TRUE, validate_evidence

NOW = dt.datetime(2026, 11, 1, 20, 0, tzinfo=dt.timezone.utc)
SHA = "a" * 40
REVISION = "sbi-dashboard-00016-safe"


def evidence():
    obj = {
        "release_class": "REPORTING_ONLY",
        "project": "meghraj-reconciliation",
        "region": "asia-south1",
        "service": "sbi-dashboard",
        "source_sha": SHA,
        "qa_source_sha": SHA,
        "release_policy": "AUTO_AFTER_ALL_GATES",
        "release_review_status": "APPROVED",
        "qa_workflow_run_id": 123456789,
        "independent_qa_reviewer": "independent-review-identifier",
        "approved_at_utc": "2026-11-01T19:00:00Z",
        "expires_at_utc": "2026-11-02T19:00:00Z",
        "candidate_revision": REVISION,
        "tested_candidate_revision": REVISION,
        "report_snapshot_sha256": "1" * 64,
        "baseline_dataset_sha256": "2" * 64,
        "approved_header_contract_sha256": "3" * 64,
    }
    obj.update({k: True for k in REQUIRED_TRUE})
    return obj


def call(obj, *, digest=None, sha=SHA):
    raw = json.dumps(obj, sort_keys=True).encode()
    return validate_evidence(raw, digest or hashlib.sha256(raw).hexdigest(), sha, NOW)


class ReportingProductionGateTests(unittest.TestCase):
    def test_all_verified_synthetic_evidence(self):
        self.assertEqual(call(evidence()), REVISION)

    def test_every_mandatory_gate_is_strict(self):
        for field in REQUIRED_TRUE:
            for value in (False, None, 1, "true"):
                with self.subTest(field=field, value=value):
                    obj = evidence()
                    obj[field] = value
                    with self.assertRaisesRegex(ValueError, "MANDATORY_PRODUCTION_GATE"):
                        call(obj)

    def test_no_financial_or_cross_service_promotion(self):
        for field, value in (
            ("release_class", "FINANCIAL"),
            ("project", "other"),
            ("region", "us-central1"),
            ("service", "sbi-supervisor-backend"),
            ("source_sha", "b" * 40),
            ("qa_source_sha", "b" * 40),
            ("release_policy", "MANUAL"),
            ("release_review_status", "PENDING"),
        ):
            with self.subTest(field=field):
                obj = evidence()
                obj[field] = value
                with self.assertRaises(ValueError):
                    call(obj)

    def test_immutable_evidence_digest(self):
        obj = evidence()
        with self.assertRaisesRegex(ValueError, "EVIDENCE_DIGEST_MISMATCH"):
            call(obj, digest="0" * 64)
        with self.assertRaisesRegex(ValueError, "PROTECTED_EVIDENCE_DIGEST_MISSING"):
            call(obj, digest="not-a-hash")

    def test_revision_bound_to_real_user_e2e(self):
        obj = evidence()
        obj["tested_candidate_revision"] = "sbi-dashboard-00017-other"
        with self.assertRaisesRegex(ValueError, "REAL_HTTP_QA_NOT_BOUND"):
            call(obj)
        obj = evidence()
        obj["candidate_revision"] = "../../danger"
        with self.assertRaisesRegex(ValueError, "CANDIDATE_REVISION_INVALID"):
            call(obj)

    def test_stale_or_future_attestations_denied(self):
        for issued, expires in (
            ("2026-10-30T00:00:00Z", "2026-10-31T00:00:00Z"),
            ("2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z"),
            ("2026-11-01T19:00:00Z", "2026-11-10T19:00:00Z"),
            ("invalid", "2026-11-02T00:00:00Z"),
        ):
            with self.subTest(issued=issued):
                obj = evidence()
                obj["approved_at_utc"] = issued
                obj["expires_at_utc"] = expires
                with self.assertRaises(ValueError):
                    call(obj)

    def test_missing_data_sha_and_boolean_qa_run_denied(self):
        obj = evidence()
        obj["report_snapshot_sha256"] = None
        with self.assertRaisesRegex(ValueError, "DATASET_OR_CONTRACT_DIGEST"):
            call(obj)
        obj = evidence()
        obj["qa_workflow_run_id"] = True
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_QA_RUN"):
            call(obj)


if __name__ == "__main__":
    unittest.main()
