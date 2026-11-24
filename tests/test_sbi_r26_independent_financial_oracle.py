"""R26 independent QA, entirely fictitious SYN- identifiers, no real finance."""
import sys
import unittest
from dataclasses import replace
from datetime import date
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
from sbi_r26_independent_financial_oracle import (
    Invoice, Payment, Edge, R26Refusal, amount, money_hypotheses,
    pair_review, global_reservation_review, source_delta_gate,
    release_readiness,
)

def inv(**kw):
    i=Invoice("SYN-MXP-001", "0001", "SYNTHETIC ALPHA", "1000.00", "90.00",
              "90.00", "1180.00", "1180.00", date(2026,9,1), ("2026-09",))
    return replace(i, **kw)

def pay(**kw):
    p=Payment("SYN-PAY-001", "0001", "SYNTHETIC ALPHA", "1160.00",
              date(2026,9,15), ("2026-09",), ("SYN-MXP-001",))
    return replace(p, **kw)

def edge(**kw):
    return replace(Edge("SYN-PAY-001","SYN-MXP-001","100.00","STANDARD"),**kw)


class TestR26IndependentFinancialOracle(unittest.TestCase):
    def test_01_exact_tds_zero_to_three_percent(self):
        for rate,credit in [(0,"1180"),(1,"1170"),(2,"1160"),(3,"1150")]:
            with self.subTest(rate=rate):
                self.assertEqual(money_hypotheses(pay(credit=credit),inv()),(rate,))

    def test_02_round_half_up_three_percent_105_50(self):
        i=inv(taxable="105.50",cgst="6.25",sgst="6.25",gross="118.00",outstanding="118.00")
        self.assertEqual(money_hypotheses(pay(credit="114.83"),i),(3,))

    def test_03_refuse_float_and_boolean(self):
        for value in (1.2,True,False,None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(R26Refusal,"UNSAFE_MONEY_TYPE"):
                    amount(value)

    def test_04_refuse_subcent_and_nonfinite(self):
        for value in ("1.005","NaN","Infinity","-Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(R26Refusal,"NONFINITE_OR_SUBCENT_MONEY"):
                    amount(value)

    def test_05_exact_pair_is_review_not_allocation(self):
        r=pair_review(pay(),inv())
        self.assertEqual(r["evidence_decision"],"CANDIDATE_INDEPENDENT_REVIEW_ONLY")
        self.assertEqual(r["tds_rates_hypotheses_only"],(2,))
        self.assertIsNone(r["financial_status"])
        self.assertFalse(r["payment_allocation_executed"])
        self.assertTrue(r["financial_apply_locked"])

    def test_06_duplicate_payment_original_k_protects(self):
        r=pair_review(pay(original_k="OK"),inv())
        self.assertIn("ORIGINAL_BANK_K_REQUIRES_LEDGER_REVIEW",r["reason_codes"])

    def test_07_invoice_s_numeric_zero_is_protected(self):
        r=pair_review(pay(),inv(source_s_marker=0))
        self.assertIn("ORIGINAL_INVOICE_S_NONBLANK_PROTECTED",r["reason_codes"])

    def test_08_invoice_s_string_zero_is_protected(self):
        r=pair_review(pay(),inv(source_s_marker="0"))
        self.assertIn("ORIGINAL_INVOICE_S_NONBLANK_PROTECTED",r["reason_codes"])

    def test_09_missing_or_contradictory_mxp_ref_holds(self):
        for refs in ((),("SYN-MXP-002",),("SYN-MXP-001","SYN-MXP-002")):
            with self.subTest(refs=refs):
                self.assertIn("MXP_REFERENCE_MISSING_OR_CONTRADICTORY",
                    pair_review(pay(mxp_refs=refs),inv())["reason_codes"])

    def test_10_non_synthetic_reference_is_refused(self):
        with self.assertRaisesRegex(R26Refusal,"UNTRUSTED_MXP_REFERENCE"):
            pair_review(pay(mxp_refs=("MXP10001",)),inv())

    def test_11_same_sol_text_not_numeric_equivalence(self):
        r=pair_review(pay(sol="1"),inv(sol="0001"))
        self.assertIn("SBISA_EXCEPTION_REQUIRES_DOCUMENTED_APPROVAL",r["reason_codes"])

    def test_12_cross_sol_without_approved_exception_holds(self):
        r=pair_review(pay(sol="0002"),inv())
        self.assertIn("CROSS_SOL_NOT_APPROVED",r["reason_codes"])

    def test_13_sbisa_blank_invoice_sol_does_not_auto_pass(self):
        r=pair_review(pay(sol="1"),inv(sol=""))
        self.assertIn("SBISA_BLANK_SOL_REQUIRES_APPROVAL",r["reason_codes"])

    def test_14_client_conflict_holds(self):
        r=pair_review(pay(client="SYNTHETIC OTHER"),inv())
        self.assertIn("CLIENT_IDENTITY_CONFLICT",r["reason_codes"])

    def test_15_payment_before_invoice_holds(self):
        r=pair_review(pay(bank_date=date(2026,8,1)),inv())
        self.assertIn("BANK_BEFORE_INVOICE_DATE",r["reason_codes"])

    def test_16_multi_month_complete_coverage_retained(self):
        i=inv(service_periods=("2026-03","2026-04","2026-05"))
        p=pay(service_periods=("2026-03","2026-04","2026-05"))
        self.assertNotIn("MULTI_MONTH_COVERAGE_INCOMPLETE",pair_review(p,i)["reason_codes"])

    def test_17_multi_month_partial_coverage_holds(self):
        i=inv(service_periods=("2026-03","2026-04","2026-05"))
        p=pay(service_periods=("2026-03",))
        self.assertIn("MULTI_MONTH_COVERAGE_INCOMPLETE",pair_review(p,i)["reason_codes"])

    def test_18_conflicting_service_month_holds(self):
        self.assertIn("SERVICE_PERIOD_CONFLICT",
                      pair_review(pay(service_periods=("2026-08",)),inv())["reason_codes"])

    def test_19_gst_later_requires_independent_ledger(self):
        self.assertIn("GST_COMPONENT_REQUIRES_SEPARATE_LEDGER_PROOF",
                      pair_review(pay(credit="180.00",gst_narration=True),inv())["reason_codes"])

    def test_20_non_boolean_gst_provenance_refused(self):
        with self.assertRaisesRegex(R26Refusal,"GST_PROVENANCE_MUST_BE_BOOLEAN"):
            pair_review(pay(gst_narration="yes"),inv())

    def test_21_negative_payment_not_a_candidate(self):
        r=pair_review(pay(credit="-10.00"),inv())
        self.assertIn("NONPOSITIVE_CREDIT",r["reason_codes"])

    def test_22_wrong_invoice_total_fails_closed(self):
        with self.assertRaisesRegex(R26Refusal,"GROSS_COMPONENTS_NOT_CONSERVED"):
            pair_review(pay(),inv(gross="1179.99"))

    def test_23_outstanding_above_gross_refused(self):
        with self.assertRaisesRegex(R26Refusal,"OUTSTANDING_OVER_GROSS"):
            pair_review(pay(),inv(outstanding="9999.99"))

    def test_24_reject_real_bank_invoice_ids(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_INVOICE_REQUIRED"):
            pair_review(pay(),inv(key="MXP19970"))

    def test_25_reject_real_payment_row(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_PAYMENT_REQUIRED"):
            pair_review(pay(key="14415"),inv())

    def test_26_single_valid_capacity_is_only_synthetic(self):
        r=global_reservation_review([pay()],[inv()],[edge()])
        self.assertTrue(r["review_capacity_pass"])
        self.assertEqual(r["real_payments_allocated"],0)
        self.assertIsNone(r["financial_status"])
        self.assertFalse(r["v251_method_parity_certified"])

    def test_27_over_reserve_one_payment_across_two_invoices(self):
        p=pay(credit="1160")
        i1=inv(outstanding="1180")
        i2=inv(key="SYN-MXP-002",outstanding="1180")
        edges=[edge(reservation="700"),edge(invoice_key="SYN-MXP-002",reservation="700")]
        r=global_reservation_review([p],[i1,i2],edges)
        self.assertIn("GLOBAL_CREDIT_OVERALLOCATED",r["reason_codes"])

    def test_28_over_reserve_same_invoice_from_two_payments(self):
        p2=pay(key="SYN-PAY-002",credit="1160.00")
        r=global_reservation_review([pay(),p2],[inv(outstanding="300")],
                                    [edge(reservation="200"),edge(payment_key="SYN-PAY-002",reservation="200")])
        self.assertIn("INVOICE_OVERALLOCATED",r["reason_codes"])

    def test_29_duplicate_invoice_id_blocks(self):
        r=global_reservation_review([pay()],[inv(),inv()],[])
        self.assertIn("DUPLICATE_SOURCE_INVOICE_NO",r["reason_codes"])

    def test_30_duplicate_payment_source_id_blocks(self):
        r=global_reservation_review([pay(),pay()],[inv()],[])
        self.assertIn("DUPLICATE_SOURCE_BANK_ROW",r["reason_codes"])

    def test_31_duplicate_graph_edge_blocks(self):
        r=global_reservation_review([pay()],[inv()],[edge(),edge()])
        self.assertIn("DUPLICATE_RESERVATION_EDGE",r["reason_codes"])

    def test_32_nonpositive_reservation_held(self):
        r=global_reservation_review([pay()],[inv()],[edge(reservation="0")])
        self.assertIn("NONPOSITIVE_RESERVATION",r["reason_codes"])

    def test_33_waterfall_before_global_held(self):
        r=global_reservation_review([pay()],[inv()],[edge(method="WATERFALL")])
        self.assertIn("WATERFALL_BEFORE_GLOBAL_ADJUDICATION",r["reason_codes"])

    def test_34_waterfall_not_last_held(self):
        r=global_reservation_review([pay()],[inv()],
            [edge(reservation="100",method="GLOBAL_ADJUDICATION"),
             edge(reservation="100",method="WATERFALL"),
             edge(reservation="100",method="STANDARD")])
        self.assertIn("WATERFALL_NOT_LAST",r["reason_codes"])

    def test_35_protected_bank_and_invoice_cannot_be_reserved(self):
        r=global_reservation_review([pay(original_k="OK")],[inv(source_s_marker=0)],[edge()])
        self.assertIn("PROTECTED_BANK_K",r["reason_codes"])
        self.assertIn("PROTECTED_INVOICE_S",r["reason_codes"])

    def test_36_unknown_invoice_edge_held(self):
        r=global_reservation_review([pay()],[inv()],[edge(invoice_key="SYN-MXP-999")])
        self.assertIn("UNKNOWN_PAYMENT_OR_INVOICE_EDGE",r["reason_codes"])

    def test_37_unknown_method_refused(self):
        with self.assertRaisesRegex(R26Refusal,"UNAPPROVED_METHOD_NAME"):
            global_reservation_review([pay()],[inv()],[edge(method="APPLY_TO_BANK")])

    def test_38_same_source_hash_precondition(self):
        h=sha256(b"SYNTHETIC ONLY").hexdigest()
        a=source_delta_gate(h,h)
        self.assertTrue(a["source_hashes_identical"])
        self.assertFalse(a["automatic_historical_OK_copying"])

    def test_39_different_source_hash_cannot_claim_272_parity(self):
        a=source_delta_gate("a"*64,"b"*64)
        self.assertEqual(a["status"],"DIFFERENT_SOURCE_NO_FINANCIAL_STATUS_PARITY")
        self.assertFalse(a["v251_certified"])

    def test_40_malformed_source_hash_refused(self):
        with self.assertRaisesRegex(R26Refusal,"EXACT_SOURCE_SHA256_REQUIRED"):
            source_delta_gate("bad","a"*64)

    def test_41_no_caller_can_claim_certified_v251(self):
        r=release_readiness()
        self.assertFalse(r["complete_master_v251_executable_certified"])
        self.assertFalse(r["real_financial_source_ledger_oracle_passed"])
        self.assertFalse(r["production_release_authorized"])
        self.assertTrue(r["financial_apply_locked"])

    def test_42_repeat_review_is_deterministic_no_ledger_mutation(self):
        p,i=pay(),inv()
        e=edge()
        first=(pair_review(p,i),global_reservation_review([p],[i],[e]))
        second=(pair_review(p,i),global_reservation_review([p],[i],[e]))
        self.assertEqual(first,second)
        self.assertEqual(e.reservation,"100.00")


if __name__ == "__main__":
    unittest.main()
