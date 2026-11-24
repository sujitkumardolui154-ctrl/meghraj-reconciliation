"""D-028 existing Payment Evidence screen compatibility, SYNTHETIC SOURCE QA.

These tests read only public repository source text. They never open prior
invoices, bank statements, real receipts or deploy an AWS container.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODFILE = ROOT / "staging/aws_login_v150/d028_existing_payment_contract.py"
spec = importlib.util.spec_from_file_location("d028_existing_payment_contract", MODFILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sources():
    return [
        (ROOT / "dashboard_source/index.html").read_text(),
        (ROOT / "staging/aws_login_v150/app.py").read_text(),
        (ROOT / "staging/aws_login_v150/payment_evidence_upload.py").read_text(),
    ]


class ExistingPaymentUiContractTests(unittest.TestCase):
    def test_existing_single_ui_reused_and_all_four_endpoints_source_present(self):
        actual = mod.source_check(ROOT)
        self.assertEqual(actual["result"], "SOURCE_COMPATIBILITY_ONLY_PASS")
        self.assertEqual(actual["existing_payment_reconciliation_ui"], "REUSE_NOT_REBUILD")
        self.assertEqual(actual["existing_routes_found"], 4)
        self.assertEqual(actual["fixed_payment_upload_headers"],
                         ["Description", "SOL ID", "Credit Amount"])
        self.assertFalse(actual["existing_UI_duplicate_created"])
        self.assertEqual(actual["aws_route"], "NOT_VERIFIED")
        self.assertEqual(actual["historical_financial_records"], "NOT_READ")
        self.assertEqual(actual["financial_writes"], "NOT_PERFORMED")
        self.assertEqual(actual["reconciliation_execution"], "NOT_PERFORMED")
        self.assertEqual(actual["d027_12_column_synthetic_adapter"], "NOT_CONNECTED_INCOMPATIBLE")

    def test_duplicate_existing_payment_form_is_denied(self):
        html, app, upload = sources()
        mutated = html.replace('id="dil-payment-upload-form"',
                               'id="dil-payment-upload-form" id="dil-payment-upload-form"')
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(mutated, app, upload)

    def test_financial_run_button_cannot_be_enabled(self):
        html, app, upload = sources()
        mutated = html.replace('id="dil-payment-reconcile" disabled',
                               'id="dil-payment-reconcile"')
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(mutated, app, upload)

    def test_unapproved_ui_endpoint_replacement_is_denied(self):
        html, app, upload = sources()
        mutated = html.replace('/api/payment-evidence/upload',
                               '/api/payment-reconciliation/run')
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(mutated, app, upload)

    def test_wrong_legacy_paymnet_12_column_contract_not_silently_used(self):
        html, app, upload = sources()
        mutated = upload.replace(
            'HEADERS = ("Description", "SOL ID", "Credit Amount")',
            'HEADERS = ("PAYMNENT", "Legacy A-L")')
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(html, app, mutated)

    def test_missing_auth_hooks_or_csrf_is_denied(self):
        html, app, upload = sources()
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app.replace("install_sessions(app)", ""), upload)
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app, upload.replace("csrf_valid()", "True"))

    def test_storage_separation_and_receipt_scope_are_mandatory(self):
        html, app, upload = sources()
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app, upload.replace("SBI_PAYMENT_EVIDENCE_DIR",
                                          "EXISTING_FINANCIAL_LEDGER_PATH"))
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app, upload.replace("g.dil_user.uid", "anonymous"))

    def test_missing_registration_and_financial_deny_is_blocked(self):
        html, app, upload = sources()
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app.replace("app.register_blueprint(payment_evidence)", ""),
                upload)
        with self.assertRaises(mod.ExistingPaymentEvidenceContractBlocked):
            mod.assess_existing_interface(
                html, app.replace("def disabled_financial_api(", "def not_denied("),
                upload)


if __name__ == "__main__":
    unittest.main()
