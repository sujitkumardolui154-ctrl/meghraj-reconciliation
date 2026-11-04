"""Offline evidence reconciliation and task-register safety contract."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "agent" / "task_queue.json"
AUDIT = ROOT / "agent" / "evidence_reconciliation_20261104.json"


class EvidenceRegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = json.loads(QUEUE.read_text())
        cls.audit = json.loads(AUDIT.read_text())
        cls.source = {t["id"]: t for t in cls.queue["tasks"]}
        cls.rows = {t["id"]: t for t in cls.audit["tasks"]}

    def test_all_ids_exactly_once(self):
        self.assertEqual(len(self.source), len(self.queue["tasks"]))
        self.assertEqual(len(self.rows), len(self.audit["tasks"]))
        self.assertEqual(set(self.source), set(self.rows))
        self.assertEqual(len(self.queue["tasks"]), 92)

    def test_status_and_workstream_unchanged(self):
        for ident, task in self.source.items():
            row = self.rows[ident]
            with self.subTest(ident=ident):
                self.assertEqual(task["execution"], row["register_execution"])
                self.assertEqual(task["execution"], row["proposed_execution"])
                self.assertEqual(task["category"], row["workstream"])
                self.assertEqual(task["title"], row["title"])
                self.assertEqual(task.get("approval_gate", "standard"), row["approval_gate"])

    def test_evidence_not_mistaken_for_completion(self):
        done = {t["id"] for t in self.queue["tasks"] if t["execution"] in ("done", "approved")}
        self.assertEqual(done, {"N06"})
        self.assertEqual(self.audit["summary"]["proposed_status_changes"], 0)
        self.assertTrue(self.audit["policy"]["no_financial_writes"])
        self.assertTrue(self.audit["policy"]["production_untouched"])
        for task in self.audit["tasks"]:
            if task["register_execution"] not in ("done", "approved"):
                self.assertTrue(task["acceptance_gap"])

    def test_prs_are_grounded_links_not_status_flags(self):
        prefix = "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/"
        for item in self.audit["tasks"]:
            for pr in item["linked_pull_requests"]:
                self.assertTrue(pr["url"].startswith(prefix))
                self.assertTrue(pr["number"] > 0)
        self.assertTrue(self.audit["policy"]["pr_links_are_not_completion_proof"])

    def test_workstream_counts(self):
        self.assertEqual(self.audit["summary"]["total"], 92)
        self.assertEqual(self.audit["summary"]["official_workstreams"], 14)
        self.assertEqual(self.audit["summary"]["states"],
                         {"in_progress": 31, "pending": 60, "done": 1})

    def test_readiness_validator_syntax(self):
        import ast
        ast.parse((ROOT / "agent" / "readiness.py").read_text())


if __name__ == "__main__":
    unittest.main()
