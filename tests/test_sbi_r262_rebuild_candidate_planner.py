"""R26.2 entirely synthetic dry-run planner tests. NO real SBI identifiers."""
import unittest
import sys
from pathlib import Path
from dataclasses import replace
from datetime import date

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r26_independent_financial_oracle import Invoice, Payment, R26Refusal
from sbi_r262_rebuild_candidate_planner import (
    plan_synthetic_only, fixture_digest, RebuildRefusal,
)

MASTER=(("0001","SYNTHETIC ALPHA"),("0002","SYNTHETIC BETA"))

def inv(**kw):
    src=Invoice(
        "SYN-MXP-001","0001","SYNTHETIC ALPHA","1000.00","90.00",
        "90.00","1180.00","1180.00",date(2026,9,1),("2026-09",)
    )
    return replace(src,**kw)

def pay(**kw):
    src=Payment(
        "SYN-PAY-001","0001","SYNTHETIC ALPHA","1160.00",
        date(2026,9,15),("2026-09",),("SYN-MXP-001",)
    )
    return replace(src,**kw)

def run(invoices=None,payments=None,master=MASTER,**kw):
    invoices=list([inv()] if invoices is None else invoices)
    payments=list([pay()] if payments is None else payments)
    digest=fixture_digest(invoices,payments,master)
    return plan_synthetic_only(invoices,payments,master,
        expected_fixture_sha256=digest,**kw)

class R262SyntheticRebuildTests(unittest.TestCase):
    def test_01_exact_mxp_tds_edge_review_only(self):
        x=run()
        self.assertEqual(x["review_candidate_edges"],
            (("SYN-PAY-001","SYN-MXP-001","1160.00","EXACT_MXP_TDS_REVIEW"),))
        self.assertIsNone(x["financial_status"])
        self.assertEqual(x["real_financial_allocations"],0)
        self.assertTrue(x["financial_apply_locked"])

    def test_02_no_payment_rows_empty_graph(self):
        x=run(payments=[])
        self.assertEqual(x["review_candidate_edges"],())
        self.assertTrue(x["global_capacity_exact_reference_only"])

    def test_03_hypothesis_does_not_assign_ok(self):
        self.assertNotIn("'OK'",repr(run()))
        self.assertFalse(run()["complete_v251_v239_certified"])

    def test_04_dnm_unique_gross_net_candidate(self):
        x=run(payments=[pay(mxp_refs=())])
        self.assertEqual(x["review_candidate_edges"][0][3],
            "DNM01_PROVISIONAL_REVIEW")
        self.assertTrue(x["dnm_provisional_only"])

    def test_05_dnm_equal_competitor_refused(self):
        x=run(invoices=[inv(),inv(key="SYN-MXP-002")],
            payments=[pay(mxp_refs=())])
        self.assertFalse(x["review_candidate_edges"])
        self.assertEqual(x["payment_holds"][0][1],"DNM_COMPETING_RUNNER_UP")

    def test_06_dnm_delta_above_one_held(self):
        x=run(payments=[pay(mxp_refs=(),credit="1161.50")])
        self.assertEqual(x["payment_holds"][0][1],"DNM_BEST_OVER_1")

    def test_07_dnm_more_than_180_days_held(self):
        x=run(payments=[pay(mxp_refs=(),bank_date=date(2027,4,1))])
        self.assertIn("DNM_NO_CANDIDATE",x["payment_holds"][0][1])

    def test_08_numeric_zero_invoice_s_protected(self):
        x=run(invoices=[inv(source_s_marker=0)])
        self.assertIn("PROTECTED_ORIGINAL_K_OR_S",x["payment_holds"][0][1])

    def test_09_original_payment_k_protected(self):
        x=run(payments=[pay(original_k="OK")])
        self.assertEqual(x["payment_holds"][0][1],"ORIGINAL_BANK_K_PROTECTED")

    def test_10_cross_sol_hold(self):
        x=run(payments=[pay(sol="0002")])
        self.assertEqual(x["payment_holds"][0][1],
            "SBISA_CROSS_SOL_REQUIRES_AUTHORIZATION")

    def test_11_client_different_hold(self):
        x=run(payments=[pay(client="SYNTHETIC OTHER")])
        self.assertIn("CLIENT_IDENTITY_CONFLICT",x["payment_holds"][0][1])

    def test_12_wrong_exact_mxp_not_fuzzy(self):
        x=run(payments=[pay(mxp_refs=("SYN-MXP-999",))])
        self.assertEqual(x["payment_holds"][0][1],"EXACT_MXP_REFERENCE_UNAVAILABLE")

    def test_13_real_id_never_enters_rebuild(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_INVOICE_REQUIRED"):
            run(invoices=[inv(key="MXP10001")])

    def test_14_master_numeric_sol_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"SYNTHETIC_MASTER_ONLY"):
            run(master=((1,"SYNTHETIC ALPHA"),))

    def test_15_master_conflicting_names_refused(self):
        master=MASTER+(("0001","SYNTHETIC WRONG"),)
        with self.assertRaisesRegex(RebuildRefusal,"CONFLICTING_MASTER_OFFICIAL_NAMES"):
            run(master=master)

    def test_16_apply_unlock_never_allowed(self):
        with self.assertRaisesRegex(RebuildRefusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            run(financial_apply="ENABLED")

    def test_17_missing_manifest_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"EXPLICIT_FIXTURE_SHA_REQUIRED"):
            plan_synthetic_only([inv()],[pay()],MASTER,expected_fixture_sha256="")

    def test_18_stale_manifest_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"FIXTURE_SHA256_MISMATCH"):
            plan_synthetic_only([inv()],[pay()],MASTER,
                expected_fixture_sha256="a"*64)

    def test_19_duplicate_payment_key_quarantines(self):
        x=run(payments=[pay(),pay()])
        self.assertFalse(x["review_candidate_edges"])
        self.assertFalse(x["global_capacity_exact_reference_only"])

    def test_20_duplicate_invoice_key_quarantines(self):
        x=run(invoices=[inv(),inv()])
        self.assertFalse(x["review_candidate_edges"])
        self.assertIn("DUPLICATE_INVOICE_QUARANTINE",x["payment_holds"][0][1])

    def test_21_two_payments_over_same_outstanding_blocked(self):
        x=run(payments=[pay(),pay(key="SYN-PAY-002")])
        self.assertFalse(x["global_capacity_exact_reference_only"])
        self.assertEqual(len(x["review_candidate_edges"]),0)

    def test_22_no_exact_tds_hypothesis_holds(self):
        x=run(payments=[pay(credit="1160.01")])
        self.assertEqual(x["payment_holds"][0][1],"INDEPENDENT_TDS_ORACLE_HOLD")

    def test_23_multi_month_complete_coverage_possible(self):
        x=run(invoices=[inv(service_periods=("2026-03","2026-04","2026-05"))],
             payments=[pay(service_periods=("2026-03","2026-04","2026-05"))])
        self.assertEqual(len(x["review_candidate_edges"]),1)

    def test_24_multi_month_incomplete_hold(self):
        x=run(invoices=[inv(service_periods=("2026-03","2026-04","2026-05"))],
             payments=[pay(service_periods=("2026-05",))])
        self.assertEqual(x["payment_holds"][0][1],"SERVICE_PERIOD_COVERAGE_MISSING")

    def test_25_gst_later_needs_ledger_proof(self):
        x=run(payments=[pay(gst_narration=True)])
        self.assertEqual(x["payment_holds"][0][1],"GST_SOURCE_PROOF_REQUIRED")

    def test_26_nonpositive_bank_credit_hold(self):
        x=run(payments=[pay(credit="-1.00")])
        self.assertEqual(x["payment_holds"][0][1],"NONPOSITIVE_CREDIT")

    def test_27_explicit_mxp_multiple_refs_hold(self):
        x=run(payments=[pay(mxp_refs=("SYN-MXP-001","SYN-MXP-002"))])
        self.assertEqual(x["payment_holds"][0][1],"MULTIPLE_MXP_REFERENCES")

    def test_28_exact_text_sol_not_padded_automatically(self):
        x=run(payments=[pay(sol="1")])
        self.assertEqual(x["payment_holds"][0][1],
            "SBISA_CROSS_SOL_REQUIRES_AUTHORIZATION")

    def test_29_identical_fixture_input_permutation_stable(self):
        a=pay();b=pay(key="SYN-PAY-002",mxp_refs=())
        x=run(payments=[a,b])
        y=run(payments=[b,a])
        self.assertEqual(x,y)

    def test_30_no_partial_waterfall_claim(self):
        x=run()
        self.assertFalse(x["partial_waterfall_implemented"])
        self.assertFalse(x["approved_sbisa_or_cross_sol_implemented"])
        self.assertFalse(x["authoritative_oct27_master_data_loaded"])
        self.assertEqual(x["production_database_writes"],0)
        self.assertFalse(x["production_release_authorized"])

if __name__=="__main__":
    unittest.main()
