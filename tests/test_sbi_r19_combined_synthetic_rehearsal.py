"""R19 synthetic end-to-end source-to-review Excel QA. No bank data or DB."""
import hashlib
import io
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import sbi_r19_combined_synthetic_rehearsal as r19


def fixture():
    return r19.build_synthetic_fixture()


def run(source=None, master=None):
    default_src, default_master = fixture()
    source = default_src if source is None else source
    master = default_master if master is None else master
    return r19.combined_synthetic_run(
        source, master,
        expected_source_sha256=hashlib.sha256(source).hexdigest(),
        expected_master_sha256=hashlib.sha256(master).hexdigest(),
    )


def change_source(fn):
    src, master = fixture()
    book = load_workbook(io.BytesIO(src))
    try:
        fn(book)
        return r19.workbook_bytes(book), master
    finally:
        book.close()


def change_master(fn):
    src, master = fixture()
    book = load_workbook(io.BytesIO(master))
    try:
        fn(book)
        return src, r19.workbook_bytes(book)
    finally:
        book.close()


class CombinedR19SyntheticRehearsalTests(unittest.TestCase):
    def test_01_full_chain_readonly_passes(self):
        r = run()
        self.assertEqual(len(r["completed_offline_stages"]), 4)
        self.assertEqual(r["stage"], "R19_SYNTHETIC_FULL_CHAIN_REHEARSAL_ONLY")

    def test_02_positive_bank_credit_all_left_suspense(self):
        r = run()
        self.assertEqual(r["output_statuses_structure_only"], {"SUSPENSE": 4})
        self.assertEqual(r["bank_source_rows"], 5)
        self.assertEqual(r["credit_evidence_counts"]["positive_unallocated"], 4)

    def test_03_nonpositive_credit_held(self):
        r = run()
        self.assertEqual(r["credit_evidence_counts"]["negative_review"], 1)
        self.assertEqual(r["review_reason_counts"]["nonpositive_credit_held"], 1)

    def test_04_exact_tds_candidate_not_paid(self):
        r = run()
        self.assertEqual(r["review_reason_counts"]["candidate_for_independent_review_only"], 1)
        self.assertEqual(r["financial_statuses_approved"], 0)

    def test_05_sbisa_collector_sol_crossing_held(self):
        r = run()
        self.assertEqual(r["review_reason_counts"]["hold_SBISA_COLLECTING_SOL_REVIEW"], 1)

    def test_06_invoice_S_zero_protected(self):
        r = run()
        self.assertEqual(r["protected_invoice_marker_rows"], 1)
        self.assertEqual(r["review_reason_counts"]["hold_INVOICE_S_NONBLANK_PROTECTED"], 1)

    def test_07_previous_ok_not_carried_into_model(self):
        r = run()
        self.assertEqual(
            r["review_reason_counts"]["hold_BANK_SOURCE_STATUS_REQUIRES_INDEPENDENT_VERIFICATION"], 1
        )
        self.assertEqual(r["output_statuses_structure_only"], {"SUSPENSE": 4})

    def test_08_capacity_invariant_no_real_allocation(self):
        r = run()
        self.assertTrue(r["one_capacity_hypothesis_checked"])
        self.assertEqual(r["real_financial_allocations"], 0)

    def test_09_original_payments_and_invoices_unchanged(self):
        r = run()
        self.assertTrue(r["output_original_cells_unchanged"])
        self.assertEqual(r["output_model_payment_columns"], "M:W")
        self.assertEqual(r["output_model_invoice_columns"], "AI:AM")

    def test_10_report_53_duplicate_headers_preserved(self):
        self.assertTrue(run()["report_53_header_order_preserved"])

    def test_11_real_firebase_gate_explicitly_unverified(self):
        r = run()
        self.assertFalse(r["real_firebase_app_session_tested"])
        self.assertIn("R14_REAL_FIREBASE_TO_FLASK_SESSION_NOT_VERIFIED", r["pending_real_release_gates"])

    def test_12_certified_v251_source_explicitly_missing(self):
        r = run()
        self.assertFalse(r["engine_v251_certified"])
        self.assertIn("MASTER_V251_MATRIX_V239_EXECUTABLE_NOT_CERTIFIED", r["pending_real_release_gates"])
        self.assertEqual(r["v251_candidate_gate"], "BLOCKED_CANDIDATE_SOURCE_OR_MANIFEST_MISSING")

    def test_13_no_database_or_writer_or_apply(self):
        r = run()
        self.assertFalse(r["financial_database_connected"])
        self.assertFalse(r["production_excel_writer_connected"])
        self.assertFalse(r["production_release_ready"])
        self.assertTrue(r["financial_apply_locked"])

    def test_14_aggregate_output_has_no_invoice_id_or_client_name(self):
        r = run()
        text = repr(r)
        for confidential in ("SYN-MXP-001", "SYN-PAY-005", "SYNTHETIC ALPHA", "1160.00"):
            self.assertNotIn(confidential, text)

    def test_15_no_workbook_original_data_mutated_by_run(self):
        src, master = fixture()
        original = hashlib.sha256(src).hexdigest()
        master_digest = hashlib.sha256(master).hexdigest()
        run(src, master)
        self.assertEqual(hashlib.sha256(src).hexdigest(), original)
        self.assertEqual(hashlib.sha256(master).hexdigest(), master_digest)

    def test_16_source_hash_mismatch_refused(self):
        src, master = fixture()
        with self.assertRaisesRegex(ValueError, "SOURCE_SHA256_MISMATCH"):
            r19.combined_synthetic_run(
                src, master, expected_source_sha256="0"*64,
                expected_master_sha256=hashlib.sha256(master).hexdigest(),
            )

    def test_17_master_hash_mismatch_refused(self):
        src, master = fixture()
        with self.assertRaisesRegex(ValueError, "MASTER_SHA256_MISMATCH"):
            r19.combined_synthetic_run(
                src, master, expected_source_sha256=hashlib.sha256(src).hexdigest(),
                expected_master_sha256="0"*64,
            )

    def test_18_non_synthetic_invoice_number_refused(self):
        src, master = change_source(
            lambda book: setattr(book["Invoice Details."]["M2"], "value", "MXP19970")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"NON_SYNTHETIC_INVOICE_ROW_REFUSED"):
            run(src, master)

    def test_19_non_synthetic_bank_identifier_refused(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["D2"], "value", "14415")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"NON_SYNTHETIC_BANK_ROW_REFUSED"):
            run(src, master)

    def test_20_non_synthetic_master_client_refused(self):
        src, master = change_master(
            lambda book: setattr(book["Clean Branch Master"]["A2"], "value", "REAL SBI BRANCH")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"NON_SYNTHETIC_MASTER_ROW_REFUSED"):
            run(src, master)

    def test_21_numeric_master_SOL_refused(self):
        src, master = change_master(
            lambda book: setattr(book["Clean Branch Master"]["B2"], "value", 1)
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"NON_SYNTHETIC_MASTER_ROW_REFUSED"):
            run(src, master)

    def test_22_non_synthetic_narration_refused(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["A2"], "value", "REAL BANK TEXT")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"NON_SYNTHETIC_BANK_NARRATION_REFUSED"):
            run(src, master)

    def test_23_duplicate_bank_row_quarantined(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["D3"], "value", "SYN-PAY-001")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"DUPLICATE_SYNTHETIC_BANK_ROW"):
            run(src, master)

    def test_24_duplicate_invoice_number_quarantined(self):
        src, master = change_source(
            lambda book: setattr(book["Invoice Details."]["M3"], "value", "SYN-MXP-001")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"DUPLICATE_SYNTHETIC_INVOICE_ID"):
            run(src, master)

    def test_25_wrong_payment_headers_refused(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["I1"], "value", "Debit")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_PAYMENT_HEADER_CONTRACT_MISMATCH"):
            run(src, master)

    def test_26_wrong_invoice_headers_refused(self):
        src, master = change_source(
            lambda book: setattr(book["Invoice Details."]["Q1"], "value", "Wrong")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_INVOICE_HEADER_CONTRACT_MISMATCH"):
            run(src, master)

    def test_27_bank_credit_formula_rejected(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["I2"], "value", "=SUM(1,2)")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_FORMULA_BANK_CREDIT_UNSUPPORTED"):
            run(src, master)

    def test_28_invoice_total_formula_rejected(self):
        src, master = change_source(
            lambda book: setattr(book["Invoice Details."]["Q2"], "value", "=SUM(N2:P2)")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_FORMULA_MONEY_UNSUPPORTED"):
            run(src, master)

    def test_29_gross_component_mismatch_rejected(self):
        src, master = change_source(
            lambda book: setattr(book["Invoice Details."]["Q2"], "value", 1190)
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_INVOICE_GROSS_COMPONENT_MISMATCH"):
            run(src, master)

    def test_30_payment_period_invalid_rejected(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["C2"], "value", "September 2026")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_SOURCE_PERIOD_REQUIRED"):
            run(src, master)

    def test_31_missing_bank_date_rejected(self):
        src, master = change_source(
            lambda book: setattr(book["PAYMNENT"]["B2"], "value", None)
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"SYNTHETIC_SOURCE_DATE_REQUIRED"):
            run(src, master)

    def test_32_unapproved_master_name_quarantines_candidate(self):
        src, master = change_master(
            lambda book: setattr(book["Clean Branch Master"]["A2"], "value", "SYNTHETIC WRONG")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"MASTER_IDENTITY_GATE_NOT_PASSED"):
            run(src, master)

    def test_33_unapproved_master_sol_quarantines_candidate(self):
        src, master = change_master(
            lambda book: setattr(book["Clean Branch Master"]["B2"], "value", "0900")
        )
        with self.assertRaisesRegex(r19.R19CombinedGateError,"MASTER_IDENTITY_GATE_NOT_PASSED"):
            run(src, master)

    def test_34_fail_if_inmemory_output_promotes_OK(self):
        original = r19.synthesize_locked_output

        def corrupted(source, reviewed):
            from openpyxl import load_workbook
            w = load_workbook(io.BytesIO(original(source, reviewed)))
            w["PAYMNENT"]["M2"] = "OK"
            output = r19.workbook_bytes(w)
            w.close()
            return output

        with patch.object(r19, "synthesize_locked_output", corrupted):
            with self.assertRaisesRegex(r19.R19CombinedGateError,"FINANCIAL_STATUS_MUST_REMAIN_SUSPENSE"):
                run()

    def test_35_fail_if_inmemory_output_mutates_source_credit(self):
        original = r19.synthesize_locked_output

        def corrupted(source, reviewed):
            w = load_workbook(io.BytesIO(original(source, reviewed)))
            w["PAYMNENT"]["I2"] = 9999
            output = r19.workbook_bytes(w)
            w.close()
            return output

        with patch.object(r19, "synthesize_locked_output", corrupted):
            with self.assertRaisesRegex(ValueError, "PROTECTED_ORIGINAL_VALUE_FORMULA_FORMAT_CHANGED"):
                run()

    def test_36_wrong_report_header_order_refused(self):
        import json
        contract = json.loads(
            (ROOT / "backend_source" / "invoice_import_contract.json").read_text()
        )["headers"]
        changed = list(contract)
        changed[14], changed[15] = changed[15], changed[14]
        with self.assertRaisesRegex(ValueError, "REPORT_53_HEADER_ORDER_OR_DUPLICATE_MISMATCH"):
            run_with_headers = r19.combined_synthetic_run
            src, master = fixture()
            run_with_headers(
                src, master,
                expected_source_sha256=hashlib.sha256(src).hexdigest(),
                expected_master_sha256=hashlib.sha256(master).hexdigest(),
                report_headers=changed,
            )


if __name__=="__main__":
    unittest.main()
