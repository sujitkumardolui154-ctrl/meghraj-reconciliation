"""R26.9 Case 2.5: synthetic adversarial payment forensics and oracle QA.

Uses Case 2.3 production-shaped Python APIs with synthetic-only source rows.
No real bank workbooks, financial status writers or database connections.
"""
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from test_sbi_r269_case24_case23_review_handoff import fixture, evidence
from sbi_r269_case24_case23_review_handoff import classify_case23_shadow
from sbi_r269_case25_forensic_independent_shadow_oracle import (
    independently_verify_shadow_forensics as verify, ForensicRefusal, STAGE,
)


def sample(**kw):
    workbook,case23,workbook_hash=fixture(**kw)
    case24=classify_case23_shadow(
        workbook,case23,expected_workbook_digest=workbook_hash)
    return workbook,case23,case24,workbook_hash


def run(w,c23,c24,digest,**overrides):
    return verify(w,c23,c24,
        expected_workbook_digest=overrides.pop("workbook_hash",digest),
        expected_matrix_evidence_digest=overrides.pop(
            "matrix_hash",c23["matrix_evidence_digest"]),
        **overrides)


class Case25ForensicOracleQA(unittest.TestCase):
    def refused(self,code,data=None,**kwargs):
        w,c23,c24,d=sample() if data is None else data
        with self.assertRaisesRegex(ForensicRefusal,code):
            run(w,c23,c24,d,**kwargs)

    def test_01_end_to_end_case21_case22_case23_case24_cash(self):
        w,c23,c24,d=sample()
        x=run(w,c23,c24,d)
        self.assertEqual(x["stage"],STAGE)
        self.assertEqual(x["shadow_cash_reserved"],"1160.00")
        self.assertEqual(x["shadow_bank_unassigned"],"0.00")
        self.assertEqual(x["shadow_invoice_cash_gap_not_receivable"],"20.00")
        self.assertEqual(x["payment_rows_recomputed"],1)
        self.assertEqual(x["review_edges_recomputed"],1)

    def test_02_per_payment_documentary_gap_explicit(self):
        w,c23,c24,d=sample()
        x=run(w,c23,c24,d)
        self.assertFalse(x["verified_bank_utr_or_statement_event"])
        self.assertFalse(x["verified_external_tds_gst_credit_note_ledger"])
        self.assertFalse(x["original_source_xlsx_bytes_independently_verified"])
        self.assertFalse(x["case24_status_claim_independently_certified"])
        self.assertFalse(x["cross_upload_duplicate_reconciliation_certified"])

    def test_03_no_live_financial_status_or_writes(self):
        w,c23,c24,d=sample()
        x=run(w,c23,c24,d)
        self.assertTrue(x["financial_apply_locked"])
        self.assertFalse(x["production_release_authorized"])
        self.assertFalse(x["final_paymnent_column_m_written"])
        self.assertFalse(x["full_master_v251_matrix_v239_certified"])
        self.assertEqual(x["real_database_writes"],0)
        self.assertEqual(x["real_financial_allocations"],0)

    def test_04_forensic_row_trace_source_and_edge(self):
        w,c23,c24,d=sample()
        x=run(w,c23,c24,d)
        p=x["payment_forensics"][0]
        self.assertEqual(p["bank_source_row"],2)
        self.assertEqual(p["original_bank_credit"],"1160.00")
        self.assertEqual(p["candidate_cash_reserved"],"1160.00")
        self.assertEqual(p["case24_shadow_status"],"REVIEW_REQUIRED")
        self.assertEqual(p["edges"][0]["invoice_no"],"MXP10001")
        self.assertEqual(p["edges"][0]["invoice_source_row"],2)
        self.assertEqual(p["edges"][0]["method"],"EXACT_MXP_REVIEW")
        self.assertEqual(p["edges"][0]["documentary_authority"],"NOT_EXTERNALLY_VERIFIED")
        self.assertEqual(len(p["forensic_row_sha256"]),64)
        self.assertEqual(len(p["edges"][0]["forensic_edge_sha256"]),64)

    def test_05_repeatability_exact_same_manifest(self):
        w,c23,c24,d=sample()
        x=run(w,c23,c24,d);y=run(w,c23,c24,d)
        self.assertEqual(x["forensic_manifest_sha256"],y["forensic_manifest_sha256"])
        self.assertEqual(x["payment_forensics"],y["payment_forensics"])

    def test_06_different_upload_separate_digest(self):
        a=sample(upload="SYN-UPLOAD-A");b=sample(upload="SYN-UPLOAD-B")
        self.assertNotEqual(run(*a)["forensic_manifest_sha256"],
                            run(*b)["forensic_manifest_sha256"])

    def test_07_synthetic_approved_status_still_only_candidate(self):
        w,c23,_,d=sample()
        c24=classify_case23_shadow(
            w,c23,expected_workbook_digest=d,evidence=(evidence(),))
        x=run(w,c23,c24,d)
        self.assertEqual(x["payment_forensics"][0]["case24_shadow_status"],"OK_CANDIDATE")
        self.assertFalse(x["case24_status_claim_independently_certified"])
        self.assertFalse(x["final_paymnent_column_m_written"])

    def test_08_original_payment_source_rewrite_refused(self):
        w,c23,c24,d=sample()
        b=replace(w.banks[0],credit="1200.00")
        w=replace(w,banks=(b,))
        self.refused("ORIGINAL_SCOPED_SOURCE_DIGEST_MISMATCH",(w,c23,c24,d))

    def test_09_protected_payment_source_change_refused(self):
        w,c23,c24,d=sample()
        w=replace(w,banks=(replace(w.banks[0],original_k="OK"),))
        self.refused("ORIGINAL_SCOPED_SOURCE_DIGEST_MISMATCH",(w,c23,c24,d))

    def test_10_protected_invoice_source_change_refused(self):
        w,c23,c24,d=sample()
        w=replace(w,invoices=(replace(w.invoices[0],original_s="PAID"),))
        self.refused("ORIGINAL_SCOPED_SOURCE_DIGEST_MISMATCH",(w,c23,c24,d))

    def test_11_cross_upload_case23_snapshot_refused(self):
        a=sample(upload="SYN-UPLOAD-A")
        b=sample(upload="SYN-UPLOAD-B")
        self.refused("UNVERIFIED_OR_RELEASED_CASE23_LEDGER",
                     (a[0],b[1],a[2],a[3]))

    def test_12_cross_upload_case24_status_refused(self):
        a=sample(upload="SYN-UPLOAD-A")
        b=sample(upload="SYN-UPLOAD-B")
        self.refused("UNVERIFIED_OR_RELEASED_CASE24_STATUS",
                     (a[0],a[1],b[2],a[3]))

    def test_13_wrong_matrix_evidence_digest_refused(self):
        self.refused("UNVERIFIED_OR_RELEASED_CASE23_LEDGER",matrix_hash="c"*64)

    def test_14_bad_expected_workbook_digest_refused(self):
        self.refused("ORIGINAL_SCOPED_SOURCE_DIGEST_MISMATCH",
                     workbook_hash="c"*64)

    def test_15_forged_case23_credit_row_projection_refused(self):
        w,c23,c24,d=sample()
        old=c23["scoped_shadow_bank_rows"][0]
        c23={**c23,"scoped_shadow_bank_rows":((old[0],old[1],old[2],
            old[3],"1159.00","1.00"),)}
        self.refused("INDEPENDENT_BANK_SOURCE_ROW_PARITY_FAILURE",(w,c23,c24,d))

    def test_16_forged_invoice_cash_row_refused(self):
        w,c23,c24,d=sample()
        old=c23["scoped_shadow_invoice_cash_rows"][0]
        c23={**c23,"scoped_shadow_invoice_cash_rows":((old[0],old[1],old[2],
            old[3],"1.00","1179.00"),)}
        self.refused("INDEPENDENT_INVOICE_SOURCE_ROW_PARITY_FAILURE",(w,c23,c24,d))

    def test_17_forged_total_bank_reservation_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"shadow_reserved_cash_total":"1160.01"}
        self.refused("SHADOW_SUMMARY_DISAGREES_WITH_SOURCE",(w,c23,c24,d))

    def test_18_forged_total_unreserved_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"shadow_unassigned_credit_total":"2.00"}
        self.refused("SHADOW_SUMMARY_DISAGREES_WITH_SOURCE",(w,c23,c24,d))

    def test_19_forged_invoice_gap_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"shadow_cash_coverage_gap_not_receivable":"19.99"}
        self.refused("SHADOW_SUMMARY_DISAGREES_WITH_SOURCE",(w,c23,c24,d))

    def test_20_modified_plan_digest_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"scoped_matrix_plan_digest":"d"*64}
        self.refused("SHADOW_PLAN_FINGERPRINT_MISMATCH",(w,c23,c24,d))

    def test_21_duplicate_matrix_proposal_refused(self):
        w,c23,c24,d=sample()
        e=c23["review_edges_not_financial_allocations"][0]
        c23={**c23,"review_edges_not_financial_allocations":(e,e)}
        self.refused("MATRIX_VS_CASH_EDGE_POPULATION_MISMATCH",(w,c23,c24,d))

    def test_22_invented_bank_key_edge_refused(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        forged=e[:2]+("SYN-UNKNOWN-KEY",)+e[3:]
        c23={**c23,"scoped_shadow_edges":(forged,)}
        self.refused("CORE_EDGE_IDENTITY_OR_METHOD_INVALID",(w,c23,c24,d))

    def test_23_invented_invoice_reference_refused(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        forged=e[:3]+("MXP99999",)+e[4:]
        c23={**c23,"scoped_shadow_edges":(forged,)}
        self.refused("CORE_EDGE_IDENTITY_OR_METHOD_INVALID",(w,c23,c24,d))

    def test_24_provisional_dnm_cannot_be_cash_edge(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        forged=e[:5]+("DNM01_PROVISIONAL_NO_RESERVATION",)+e[6:]
        c23={**c23,"scoped_shadow_edges":(forged,)}
        self.refused("CORE_EDGE_IDENTITY_OR_METHOD_INVALID",(w,c23,c24,d))

    def test_25_invalid_fractional_reservation_refused(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        c23={**c23,"scoped_shadow_edges":(e[:4]+("1160.001",)+e[5:],)}
        self.refused("INVALID_SOURCE_OR_LEDGER_MONEY",(w,c23,c24,d))

    def test_26_bank_capacity_overdraw_refused(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        c23={**c23,"scoped_shadow_edges":(e[:4]+("1161.00",)+e[5:],)}
        self.refused("INDEPENDENT_BANK_CAPACITY_OVERDRAW",(w,c23,c24,d))

    def test_27_hold_on_active_cash_edge_fails(self):
        w,c23,c24,d=sample()
        c23={**c23,"matrix_payment_holds":((w.upload_id,2,("SYN-HOLD",)),)}
        self.refused("HELD_PAYMENT_HAS_SHADOW_CASH",(w,c23,c24,d))

    def test_28_competing_invoice_with_cash_fails(self):
        w,c23,c24,d=sample()
        c23={**c23,"global_competing_invoice_groups_held":("MXP10001",)}
        self.refused("CONTESTED_INVOICE_HAS_RESERVED_CASH",(w,c23,c24,d))

    def test_29_fake_quarantined_invoice_with_cash_fails(self):
        w,c23,c24,d=sample()
        c23={**c23,"matrix_invoice_quarantines":(
            (w.upload_id,2,("SYN-INVALID",)),)}
        self.refused("QUARANTINED_INVOICE_HAS_RESERVED_CASH",(w,c23,c24,d))

    def test_30_case24_final_ok_assignment_refused(self):
        w,c23,c24,d=sample()
        x=dict(c24["records"][0],final_column_m_status="OK")
        c24={**c24,"records":(x,)}
        self.refused("UNAUTHORIZED_CASE24_BANK_STATUS_RESULT",(w,c23,c24,d))

    def test_31_case24_write_permission_refused(self):
        w,c23,c24,d=sample()
        x=dict(c24["records"][0],write_column_m=True)
        c24={**c24,"records":(x,)}
        self.refused("UNAUTHORIZED_CASE24_BANK_STATUS_RESULT",(w,c23,c24,d))

    def test_32_case24_wrong_row_counter_refused(self):
        w,c23,c24,d=sample()
        c24={**c24,"shadow_status_counts":(("$FORGED",999),)}
        self.refused("CASE24_STATUS_COUNTER_MISMATCH",(w,c23,c24,d))

    def test_33_duplicate_case24_row_refused(self):
        w,c23,c24,d=sample()
        c24={**c24,"records":c24["records"]+c24["records"]}
        self.refused("CASE24_PAYMENT_STATUS_POPULATION_MISMATCH",(w,c23,c24,d))

    def test_34_case24_unsupported_status_refused(self):
        w,c23,c24,d=sample()
        x=dict(c24["records"][0],shadow_status="OK")
        c24={**c24,"records":(x,)}
        self.refused("UNAUTHORIZED_CASE24_BANK_STATUS_RESULT",(w,c23,c24,d))

    def test_35_cannot_claim_suspense_when_cash_reserved(self):
        w,c23,c24,d=sample()
        x=dict(c24["records"][0],shadow_status="SUSPENSE_CANDIDATE")
        c24={**c24,"records":(x,),
             "shadow_status_counts":(("SUSPENSE_CANDIDATE",1),)}
        self.refused("CONTRADICTORY_STATUS_AND_CASH_REVIEW",(w,c23,c24,d))

    def test_36_cannot_claim_duplicate_payment_when_cash_reserved(self):
        w,c23,c24,d=sample()
        x=dict(c24["records"][0],
               shadow_status="DUPLICATE_PAYMENT_CANDIDATE")
        c24={**c24,"records":(x,),
             "shadow_status_counts":(("DUPLICATE_PAYMENT_CANDIDATE",1),)}
        self.refused("CONTRADICTORY_STATUS_AND_CASH_REVIEW",(w,c23,c24,d))

    def test_37_dnm_unreserved_review_passes_with_zero_cash(self):
        data=sample(description="POSTAGE SEPTEMBER 2026")
        x=run(*data)
        self.assertEqual(x["shadow_cash_reserved"],"0.00")
        self.assertEqual(x["shadow_bank_unassigned"],"1160.00")
        self.assertEqual(x["review_edges_recomputed"],0)
        self.assertTrue(x["payment_forensics"][0]["case23_hold_applied"])
        self.assertFalse(x["production_release_authorized"])

    def test_38_dnm_forged_reservation_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"unreserved_dnm_candidates":(
            (w.upload_id,2,"MXP10001","DNM_REVIEW_ONLY_NEVER_RESERVE"),)}
        self.refused("HELD_PAYMENT_HAS_SHADOW_CASH",(w,c23,c24,d))

    def test_39_case23_production_writes_claim_refused(self):
        w,c23,c24,d=sample()
        c23={**c23,"real_database_writes":1}
        self.refused("UNVERIFIED_OR_RELEASED_CASE23_LEDGER",(w,c23,c24,d))

    def test_40_case24_release_claim_refused(self):
        w,c23,c24,d=sample()
        c24={**c24,"production_release_authorized":True}
        self.refused("UNVERIFIED_OR_RELEASED_CASE24_STATUS",(w,c23,c24,d))

    def test_41_nonlocked_requested_apply_refused(self):
        self.refused("FINANCIAL_APPLY_LOCK_REQUIRED",financial_apply="ENABLED")

    def test_42_unknown_method_refused(self):
        w,c23,c24,d=sample()
        e=c23["scoped_shadow_edges"][0]
        c23={**c23,"scoped_shadow_edges":(e[:5]+("WATERFALL_REVIEW",)+e[6:],)}
        self.refused("CORE_EDGE_IDENTITY_OR_METHOD_INVALID",(w,c23,c24,d))


if __name__ == "__main__":
    unittest.main()
