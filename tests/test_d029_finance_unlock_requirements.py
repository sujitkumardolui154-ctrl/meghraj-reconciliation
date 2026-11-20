"""D-029: owner historical-freeze and transparent financial unlock QA.

Only mocked Firebase sessions and fabricated in-memory release contracts.
Never read bank, invoice, credit-note, GST, allocation or real financial data.
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
for folder in (
    ROOT / "dashboard_source",
    ROOT / "staging/aws_login_v150",
    ROOT / "staging/railway_public",
    ROOT / "backend_source",
):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

spec = importlib.util.spec_from_file_location(
    "d029_financial_unlock_app", ROOT / "staging/aws_login_v150/app.py"
)
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

from reconciliation_readiness import _base_response, _unlock_requirements


class D029FinanceUnlockRequirementsTests(unittest.TestCase):
    def setUp(self):
        appmod.app.testing = True
        self.client = appmod.app.test_client()
        self.client.set_cookie("__Host-dil_session", "synthetic-only", secure=True)

    def test_five_blockers_and_historical_freeze(self):
        result = _base_response()
        self.assertFalse(result["unlock_allowed"])
        self.assertFalse(result["financial_writes"])
        self.assertFalse(result["reconciliation_executed"])
        self.assertFalse(result["historical_financial_read_authorized"])
        self.assertFalse(result["historical_financial_write_authorized"])
        self.assertFalse(result["historical_reconciliation_authorized"])
        self.assertFalse(result["synthetic_qa_is_production_approval"])
        self.assertEqual(result["execution_mode"], "FINANCIAL_APPLY_BLOCKED")
        self.assertEqual(result["eligible_future_only_scope"], "NOT_YET_CERTIFIED")
        self.assertEqual(result["existing_payment_evidence_format"],
                         ["Description", "SOL ID", "Credit Amount"])
        requirements = result["unlock_requirements"]
        self.assertEqual(len(requirements), 5)
        self.assertEqual(
            len(set(x["id"] for x in requirements)), 5)
        self.assertTrue(all(x["status"] == "BLOCKED" for x in requirements))
        self.assertEqual(requirements, _unlock_requirements())

    def test_mandatory_date_and_utr_in_new_only_contract(self):
        requirement = next(
            x for x in _unlock_requirements()
            if x["id"] == "NEW_PAYMENT_IDENTITY_AND_DATE"
        )
        self.assertIn("UTR", requirement["explanation"])
        self.assertIn("date", requirement["explanation"])
        self.assertIn("activation cutoff", requirement["required_work"])
        self.assertIn("Credit-I", requirement["required_work"])

    def test_new_only_ledger_and_canonical_engine_cannot_be_claimed(self):
        requirements = {x["id"]: x for x in _unlock_requirements()}
        self.assertIn("POST_ACTIVATION_INVOICE_AND_LEDGER", requirements)
        self.assertIn("CANONICAL_ALLOCATOR", requirements)
        self.assertIn("TRANSACTIONAL_WRITER_AND_REVIEW", requirements)
        self.assertIn("INDEPENDENT_RELEASE_EVIDENCE", requirements)
        self.assertIn("never mounts", requirements["POST_ACTIVATION_INVOICE_AND_LEDGER"]["required_work"])

    def test_get_status_is_authenticated_and_denies_unlock(self):
        unauthenticated = appmod.app.test_client()
        self.assertEqual(
            unauthenticated.get("/api/payment-reconciliation/status").status_code,
            401)
        user = SimpleNamespace(
            uid="SYNTH-USER", email="qa@example.invalid",
            disabled=False, display_name="Synthetic QA",
            custom_claims={"dil_dashboard": True}
        )
        with patch("dashboard_sessions.firebase_app", return_value=None), \
             patch("dashboard_sessions.auth.verify_session_cookie",
                   return_value={"uid": "SYNTH-USER"}), \
             patch("dashboard_sessions.auth.get_user", return_value=user):
            result = self.client.get("/api/payment-reconciliation/status")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["state"], "BLOCKED_PRODUCTION_DEPENDENCIES")
            self.assertEqual(len(result.json["unlock_requirements"]), 5)
            self.assertFalse(result.json["unlock_allowed"])
            self.assertFalse(result.json["financial_writes"])
            self.assertFalse(result.json["historical_financial_read_authorized"])
            self.assertEqual(
                self.client.post("/api/payment-reconciliation/run").status_code,
                403)

    def test_ui_exposes_only_readiness_diagnostic_not_apply(self):
        html = (ROOT / "dashboard_source/index.html").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="dil-finance-unlock-status"'), 1)
        self.assertEqual(html.count('id="dil-finance-unlock-result"'), 1)
        self.assertEqual(html.count('id="dil-finance-unlock-details"'), 1)
        self.assertIn('id="dil-payment-reconcile" disabled', html)
        self.assertIn('id="dil-payment-readiness" disabled', html)
        self.assertIn('await call("/api/payment-reconciliation/status")', html)
        self.assertIn('result.unlock_allowed !== false', html)
        self.assertIn('heading.textContent = String(item.id', html)
        self.assertIn('list.appendChild(li)', html)
        self.assertNotIn('id="dil-finance-apply-submit"', html)


if __name__ == "__main__":
    unittest.main()
