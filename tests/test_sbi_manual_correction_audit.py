"""Synthetic, fail-closed tests for the 69-task manual correction register."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sbi_manual_correction_audit", ROOT / "tools" / "sbi_manual_correction_audit.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
QUEUE = json.loads((ROOT / "agent" / "task_queue.json").read_text(encoding="utf-8"))
PLAN = json.loads((ROOT / "agent" / "manual_correction_plan.json").read_text(encoding="utf-8"))


class ManualCorrectionTests(unittest.TestCase):
    def check(self, queue=None, plan=None):
        return audit.validate(queue or QUEUE, plan or PLAN)

    def test_pending_full_coverage_and_finance_lock(self):
        result = self.check()
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["total"], 92)
        self.assertEqual(result["pending_triaged"], 69)
        self.assertEqual(result["financial_execution"], "RESTRICTED")
        self.assertEqual(result["database_writes"], "DISABLED")
        self.assertEqual(result["source_changes"], 0)

    def test_duplicated_manual_task_rejected(self):
        plan = deepcopy(PLAN)
        plan["items"].append(deepcopy(plan["items"][0]))
        self.assertIn("duplicate_manual_id", self.check(plan=plan)["errors"])

    def test_missing_task_rejected(self):
        plan = deepcopy(PLAN)
        plan["items"].pop()
        self.assertIn("pending_coverage_mismatch", self.check(plan=plan)["errors"])

    def test_mislabeled_task_execution_rejected(self):
        plan = deepcopy(PLAN)
        plan["items"][0]["manual_review"] = "complete"
        self.assertIn("premature_execution_claim", self.check(plan=plan)["errors"])

    def test_write_gate_cannot_be_downgraded(self):
        plan = deepcopy(PLAN)
        item = next(x for x in plan["items"] if x["id"] == "B01")
        item["approval_gate"] = "standard"
        item["lane"] = "A_DASHBOARD"
        item["priority"] = "P2"
        result = self.check(plan=plan)
        self.assertIn("approval_gate_mismatch", result["errors"])
        self.assertIn("financial_approval_mismatch", result["errors"])

    def test_missing_acceptance_and_policy_tamper_fail(self):
        plan = deepcopy(PLAN)
        plan["items"][0]["required_evidence"] = ""
        plan["gate_policy"]["database_writes"] = "ENABLED"
        errors = self.check(plan=plan)["errors"]
        self.assertIn("incomplete_manual_instruction", errors)
        self.assertIn("restricted_policy_mismatch", errors)

    def test_task_state_change_requires_retriage(self):
        queue = deepcopy(QUEUE)
        target = next(x for x in queue["tasks"] if x["execution"] == "pending")
        target["execution"] = "in_progress"
        self.assertIn("nonpending_manual_item", self.check(queue=queue)["errors"])

    def test_no_direct_cloud_or_financial_operations(self):
        text = (ROOT / "tools" / "sbi_manual_correction_audit.py").read_text(encoding="utf-8")
        for forbidden in ("firebase_admin", "firestore.Client(", "docker compose up",
                          "gcloud run deploy", "git push", "requests.post(",
                          "subprocess.run(", "os.system("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
