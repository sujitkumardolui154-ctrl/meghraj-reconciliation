import json
import unittest
from pathlib import Path
from agent.consolidated_controller import evaluate, choose_tests

ROOT = Path(__file__).resolve().parents[1]

class AgenticGateTests(unittest.TestCase):
    def test_master_queue(self):
        data = json.loads((ROOT / "agent/task_queue.json").read_text())
        result = evaluate(data)
        self.assertEqual(result["task_total"], 88)
        self.assertFalse(result["financial_write_permitted"])
        self.assertFalse(result["traffic_promotion_permitted"])
        self.assertFalse(result["coding_agent_configured"])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            evaluate({"tasks": [{"id":"A01", "execution":"pending"}] * 2})

    def test_finance_coverage(self):
        names = [t[0] for t in choose_tests(["backend_source/payment_engine.py"], False)]
        self.assertIn("financial_contract", names)

    def test_auth_coverage(self):
        names = [t[0] for t in choose_tests(["dashboard_source/dashboard_sessions.py"], False)]
        self.assertIn("credit_note_auth", names)

    def test_shared_agent_change_triggers_all(self):
        self.assertEqual(len(choose_tests(["agent/task_queue.json"], False)), 4)

    def test_no_fabricated_release(self):
        self.assertEqual(len(choose_tests([], False)), 4)

if __name__ == "__main__":
    unittest.main()
