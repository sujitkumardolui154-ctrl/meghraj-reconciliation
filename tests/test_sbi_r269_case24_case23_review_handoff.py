"""End-to-end pure Case 2.1/2.2/2.3 -> Case 2.4 synthetic scope tests."""
from dataclasses import replace
from datetime import date
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))

from sbi_r267_readonly_real_candidate_engine import InvoiceInput, BankInput
from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, ScopedBank, ScopedInvoice, fresh_workbook_digest,
)
from sbi_r269_case23_master_matrix_adjudicator import (
    connect_master_matrix_review, evidence_digest,
)
from sbi_r269_case24_financial_status_shadow import StatusEvidence
from sbi_r269_case24_case23_review_handoff import (
    classify_case23_shadow, StatusIntegrationRefusal, STAGE,
)

MASTER=(("0001","SYNTHETIC ALPHA"),)
SHA="a"*64
M_SHA="b"*64


def fixture(upload="SYN-UPLOAD-A", description="POSTAGE SEPTEMBER 2026 MXP10001",
            credit="1160.00"):
    iv=(InvoiceInput(2,"MXP10001","0001","SYNTHETIC ALPHA",
        date(2026,9,1),("2026-09",),"1000.00","90.00","90.00","1180.00"),)
    pay=(BankInput(2,"0001","SYNTHETIC ALPHA",date(2026,9,15),
        ("2026-09",),description,credit),)
    wb=FreshWorkbook(upload,SHA,M_SHA,
        (ScopedInvoice(upload,iv[0].invoice_no,2,iv[0].gross,iv[0].original_s),),
        (ScopedBank(upload,"SYN-PAY-002",2,pay[0].credit,pay[0].original_k),))
    dg=fresh_workbook_digest(wb)
    case23=connect_master_matrix_review(
        wb,iv,pay,MASTER,
        expected_workbook_digest=dg,
        expected_matrix_evidence_digest=evidence_digest(iv,pay,MASTER),
        financial_apply="LOCKED")
    return wb,case23,dg


def evidence(upload="SYN-UPLOAD-A", **changes):
    return replace(StatusEvidence(upload,2,"1160.00",source_verified=True,
        unique_bank_event_verified=True,allocation_finalized=True,
        independent_allocation_oracle_passed=True,invoice_and_sol_verified=True,
        service_period_verified=True,tds_gst_credit_note_verified=True,
        fully_accounted_credit=True),**changes)


class CombinedCase24IntegrationTests(unittest.TestCase):
    def bound(self, wb, case23, digest, evidence_rows=()):
        r=classify_case23_shadow(
            wb,case23,expected_workbook_digest=digest,evidence=tuple(evidence_rows))
        self.assertEqual(r["stage"],STAGE)
        self.assertFalse(r["real_status_assignment"])
        self.assertIsNone(r["final_column_m_status"])
        self.assertEqual(r["real_payment_allocations"],0)
        self.assertEqual(r["real_database_writes"],0)
        self.assertTrue(r["financial_apply_locked"])
        self.assertFalse(r["production_release_authorized"])
        self.assertFalse(r["full_v251_v239_certified"])
        self.assertTrue(r["caller_evidence_not_independently_certified"])
        self.assertEqual(len(r["records"]),len(wb.banks))
        self.assertTrue(all(row["final_column_m_status"] is None for row in r["records"]))
        return r["records"][0]

    def test_01_full_case23_handoff_without_external_evidence_holds(self):
        self.assertEqual(self.bound(*fixture())["shadow_status"],"REVIEW_REQUIRED")
    def test_02_cash_reservation_does_not_mean_ok(self):
        wb,case23,digest=fixture()
        self.assertEqual(case23["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(self.bound(wb,case23,digest)["shadow_status"],"REVIEW_REQUIRED")
    def test_03_synthetic_all_flags_still_only_candidate(self):
        wb,case23,digest=fixture()
        self.assertEqual(self.bound(wb,case23,digest,(evidence(),))["shadow_status"],
            "OK_CANDIDATE")
    def test_04_matrix_hold_overrides_caller_claims(self):
        wb,case23,digest=fixture()
        case23={**case23,"matrix_payment_holds":((wb.upload_id,2,("SYN-HOLD",)),)}
        self.assertEqual(self.bound(wb,case23,digest,(evidence(),))["shadow_status"],
            "REVIEW_REQUIRED")
    def test_05_provisional_dnm_cannot_become_ok(self):
        wb,case23,digest=fixture(description="POSTAGE SEPTEMBER 2026")
        self.assertTrue(case23["unreserved_dnm_candidates"])
        self.assertEqual(self.bound(wb,case23,digest,(evidence(),))["shadow_status"],
            "REVIEW_REQUIRED")
    def test_06_unmatched_bank_row_cannot_claim_settlement(self):
        wb,case23,digest=fixture(description="POSTAGE SEPTEMBER 2026 MXP99999")
        self.assertEqual(case23["scoped_shadow_edges"],())
        self.assertEqual(self.bound(wb,case23,digest,(evidence(),))["shadow_status"],
            "REVIEW_REQUIRED")
    def test_07_changed_bank_credit_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"STATUS_CREDIT"):
            self.bound(wb,case23,digest,(evidence(original_credit="1161.00"),))
    def test_08_cross_upload_evidence_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"CROSS_UPLOAD"):
            self.bound(wb,case23,digest,(evidence(upload="SYN-OTHER-UPLOAD"),))
    def test_09_duplicate_evidence_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"DUPLICATE_STATUS"):
            self.bound(wb,case23,digest,(evidence(),evidence()))
    def test_10_forged_case23_paid_status_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"CASE23_UNCERTIFIED"):
            self.bound(wb,{**case23,"final_payment_status":"OK"},digest)
    def test_11_forged_case23_writes_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"CASE23_UNCERTIFIED"):
            self.bound(wb,{**case23,"real_database_writes":1},digest)
    def test_12_wrong_workbook_digest_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"SOURCE_SCOPE"):
            self.bound(wb,case23,"c"*64)
    def test_13_no_foreign_workbook_status_carry(self):
        w1,c1,d1=fixture("SYN-UPLOAD-A")
        w2,c2,d2=fixture("SYN-UPLOAD-B")
        self.assertNotEqual(d1,d2)
        self.assertEqual(self.bound(w1,c1,d1)["upload_id"],"SYN-UPLOAD-A")
        self.assertEqual(self.bound(w2,c2,d2)["upload_id"],"SYN-UPLOAD-B")
    def test_14_financial_unlock_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"LOCK"):
            classify_case23_shadow(wb,case23,expected_workbook_digest=digest,
                financial_apply="ENABLED")
    def test_15_invalid_evidence_type_refused(self):
        wb,case23,digest=fixture()
        with self.assertRaisesRegex(StatusIntegrationRefusal,"IMMUTABLE"):
            classify_case23_shadow(wb,case23,expected_workbook_digest=digest,
                evidence=[evidence()])
    def test_16_claimed_suspense_with_candidate_cash_holds(self):
        wb,case23,digest=fixture()
        x=evidence(allocation_finalized=False,certified_no_match=True)
        self.assertEqual(self.bound(wb,case23,digest,(x,))["shadow_status"],"REVIEW_REQUIRED")
    def test_17_unknown_matrix_bank_row_refused(self):
        wb,case23,digest=fixture()
        forged={**case23,"review_edges_not_financial_allocations":(
            (wb.upload_id,99,"MXP10001","EXACT_MXP_REVIEW"),)}
        with self.assertRaisesRegex(StatusIntegrationRefusal,"UNRECOGNIZED"):
            self.bound(wb,forged,digest)

if __name__ == "__main__":
    unittest.main()
