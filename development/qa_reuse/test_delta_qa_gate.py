"""R31.14 targeted offline QA reuse policy tests, no AWS or external calls."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("delta_qa_gate", HERE / "delta_qa_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class QAReusePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = gate.load_registry()
        cls.synthetic = cls.registry["source_evidence"][0]

    def run_success(self, row, run_id=None, sha=None, name=None, status="completed",
                    conclusion="success"):
        return {
            "id": run_id if run_id is not None else row["workflow_run_id"],
            "head_sha": sha or row["executed_sha"],
            "name": name or row["workflow_name"],
            "status": status, "conclusion": conclusion,
        }

    def test_manifest_exact_evidence_fingerprints_and_scope(self):
        self.assertEqual(len(self.registry["source_evidence"]), 3)
        self.assertEqual(self.synthetic["assurance_scope"], "synthetic_localhost_tls_only")
        self.assertEqual(self.registry["release"]["external_mtls"], "NOT_TESTED")
        self.assertEqual(self.registry["release"]["financial_apply"], "LOCKED")
        self.assertEqual(len(self.registry["remaining_live_gates"]), 7)

    def test_exact_run_and_exact_sha_required(self):
        e = self.synthetic
        good = self.run_success(e)
        self.assertTrue(gate.latest_workflow_verified(e, [good]))
        self.assertFalse(gate.latest_workflow_verified(
            e, [self.run_success(e, sha="b" * 40)]))
        self.assertFalse(gate.latest_workflow_verified(
            e, [self.run_success(e, name="Unrelated workflow")]))
        self.assertFalse(gate.latest_workflow_verified(
            e, [self.run_success(e, run_id=1)]))
        self.assertFalse(gate.latest_workflow_verified(
            e, [self.run_success(e, conclusion="failure")]))
        self.assertFalse(gate.latest_workflow_verified(
            e, [self.run_success(e, status="in_progress", conclusion=None)]))

    def test_newer_failure_cancels_reuse_not_bypassed(self):
        e = self.synthetic
        good = self.run_success(e)
        failure = self.run_success(
            e, run_id=e["workflow_run_id"]+20, conclusion="failure")
        self.assertFalse(gate.latest_workflow_verified(e, [good, failure]))
        self.assertTrue(gate.latest_workflow_verified(e, [failure, good],
                                                      ) is False)

    def test_exact_source_change_requires_only_targeted_qa(self):
        good = [self.run_success(self.synthetic)]
        self.assertEqual(
            gate.decision(self.synthetic, source_matches=True, runs=good),
            "REUSE_EXACT_SOURCE_GITHUB_PASS"
        )
        self.assertEqual(
            gate.decision(self.synthetic, source_matches=False, runs=good),
            "TARGETED_SOURCE_QA_REQUIRED"
        )
        self.assertEqual(
            gate.decision(self.synthetic, source_matches=True, runs=None),
            "GITHUB_EVIDENCE_UNVERIFIED"
        )

    def test_git_blob_security_cannot_reuse_changed_file(self):
        e = self.synthetic
        with patch.object(gate, "git", return_value="f" * 40):
            self.assertFalse(gate.current_blobs(e))
        first_blob = next(iter(e["source_blobs"].values()))
        with patch.object(gate, "git", return_value=first_blob):
            # Only one of many files matches - fail closed.
            self.assertFalse(gate.current_blobs(e))

    def test_status_plan_does_not_dispatch_tests(self):
        status = {x["id"]: "REUSE_EXACT_SOURCE_GITHUB_PASS"
                  for x in self.registry["source_evidence"]}
        p = gate.build_plan(self.registry, status)
        self.assertEqual(len(p["reused_existing_qa"]), 3)
        self.assertEqual(p["targeted_source_qa"], [])
        self.assertEqual(p["additional_workflows_dispatched"], 0)
        self.assertEqual(p["external_mtls"], "NOT_TESTED")
        self.assertEqual(p["separate_migration_safety"],
                         "KNOWN_GITHUB_FAILURE_REVIEW_REQUIRED")
        self.assertEqual(p["production_release"], "BLOCKED")

    def test_unmatched_status_cannot_claim_complete(self):
        with self.assertRaises(gate.GateError):
            gate.build_plan(self.registry, {"synthetic_mtls_4j": "REUSE_EXACT_SOURCE_GITHUB_PASS"})

    def test_source_pin_and_clean_checkout_required(self):
        with patch.object(gate, "git", side_effect=["a"*40, ""]):
            gate.checked_source("a"*40)
        with patch.object(gate, "git", side_effect=["a"*40, " M app.py"]):
            with self.assertRaises(gate.GateError):
                gate.checked_source("a"*40)
        with patch.object(gate, "git", return_value="b"*40):
            with self.assertRaises(gate.GateError):
                gate.checked_source("a"*40)

    def test_github_is_readonly_and_never_dispatches(self):
        calls=[]
        def fake_request(url, method, headers):
            calls.append((url,method,headers))
            return object()
        class FakeResponse:
            status=200
            def __enter__(self): return self
            def __exit__(self,*_): return False
        with patch.object(gate, "Request",side_effect=fake_request), \
             patch.object(gate, "urlopen",return_value=FakeResponse()), \
             patch.object(gate.json, "load",return_value={
                 "workflow_runs":[self.run_success(self.synthetic)]}):
            out=gate.github_runs_for_exact_sha(self.synthetic)
        self.assertEqual(out[0]["id"],self.synthetic["workflow_run_id"])
        self.assertEqual(calls[0][1],"GET")
        self.assertIn("head_sha="+self.synthetic["executed_sha"],calls[0][0])
        self.assertNotIn("/dispatches",calls[0][0])

    def test_unsafe_manifest_no_bypass(self):
        e = self.registry.copy()
        e["release"] = dict(self.registry["release"], financial_apply="ENABLED")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.json"
            import json
            p.write_text(json.dumps(e),encoding="utf-8")
            with self.assertRaises(gate.GateError):
                gate.load_registry(p)


if __name__ == "__main__":
    unittest.main()
