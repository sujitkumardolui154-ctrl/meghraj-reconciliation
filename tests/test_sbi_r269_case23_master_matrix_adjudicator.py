"""R26.9 Case 2.3 Matrix→Master read-only integration, 62 synthetic tests."""
from dataclasses import replace
from datetime import date
from unittest.mock import patch
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
import sbi_r269_case23_master_matrix_adjudicator as gate
from sbi_r267_readonly_real_candidate_engine import (
    InvoiceInput,BankInput,RelationshipProof,
)
from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook,ScopedInvoice,ScopedBank,fresh_workbook_digest,
)
from sbi_r269_core_cash_ledger_dry_run import LedgerRefusal

MASTER=(("0001","SYNTHETIC ALPHA"),("0002","SYNTHETIC BETA"),
        ("1","SYNTHETIC ALPHA"))
A="SYN-UPLOAD-A"
B="SYN-UPLOAD-B"
SHA="a"*64
MASTER_SHA="b"*64


def invoice(**kw):
    return replace(InvoiceInput(2,"MXP10001","0001","SYNTHETIC ALPHA",
        date(2026,9,1),("2026-09",),"1000.00","90.00","90.00","1180.00"),**kw)


def bank(**kw):
    return replace(BankInput(2,"0001","SYNTHETIC ALPHA",
        date(2026,9,15),("2026-09",),
        "POSTAGE SEPTEMBER 2026 MXP10001","1160.00"),**kw)


def proof(category="PARTIAL",row=2,invoice_no="MXP10001",**kw):
    return replace(RelationshipProof(row,invoice_no,category,
                   "SYN-PROOF-001",True),**kw)


def args(upload=A, invoices=None,payments=None,master=MASTER,relationships=(),
         scoped=None):
    inv=tuple([invoice()] if invoices is None else invoices)
    pay=tuple([bank()] if payments is None else payments)
    wb=FreshWorkbook(
        upload_id=upload,source_sha256=SHA,master_sha256=MASTER_SHA,
        invoices=tuple(ScopedInvoice(upload,x.invoice_no,x.source_row,
                 x.gross,x.original_s) for x in inv),
        banks=tuple(ScopedBank(upload,f"SYN-PAY-{x.source_row:03d}",
                 x.source_row,x.credit,x.original_k) for x in pay),
    ) if scoped is None else scoped
    return dict(workbook=wb,invoices=inv,payments=pay,
        master_pairs=tuple(master),relationship_proofs=tuple(relationships),
        expected_workbook_digest=fresh_workbook_digest(wb),
        expected_matrix_evidence_digest=gate.evidence_digest(
            inv,pay,tuple(master),tuple(relationships),
        ))


def run(**kw):
    return gate.connect_master_matrix_review(**args(**kw))


class MasterMatrixIntegrationQA(unittest.TestCase):
    def refused(self,reason, *, input_override=None, **kw):
        call=args(**kw) if input_override is None else input_override
        with self.assertRaisesRegex((gate.MasterMatrixRefusal,LedgerRefusal),reason):
            gate.connect_master_matrix_review(**call)

    def test_01_exact_mxp_matrix_to_master_shadow(self):
        x=run()
        self.assertEqual(x["stage"],gate.STAGE)
        self.assertEqual(x["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(len(x["scoped_shadow_edges"]),1)
    def test_02_matrix_matches_original_invoice(self):
        self.assertEqual(run()["review_edges_not_financial_allocations"][0][2],"MXP10001")
    def test_03_exact_method_selected(self):
        self.assertEqual(run()["review_edges_not_financial_allocations"][0][3],
                         "EXACT_MXP_REVIEW")
    def test_04_matrix_not_status_authority(self):
        self.assertTrue(run()["matrix_only_proposes_no_approval"])
    def test_05_master_cash_only_authority(self):
        self.assertTrue(run()["master_owns_only_scoped_cash_reservations"])
    def test_06_same_workbook_option_B(self):
        x=run()
        self.assertEqual(x["upload_mode"],"INDEPENDENT_FRESH_WORKBOOK")
        self.assertFalse(x["historical_workbooks_read"])
        self.assertFalse(x["previous_approved_allocations_imported"])
    def test_07_no_historical_status_copy(self):
        self.assertFalse(run()["previous_payment_statuses_imported"])
    def test_08_no_financial_apply(self):
        self.assertTrue(run()["financial_apply_locked"])
    def test_09_no_db_writes(self):
        self.assertEqual(run()["real_database_writes"],0)
    def test_10_no_real_reconciled_payments(self):
        self.assertEqual(run()["real_bank_payments_reconciled"],0)
        self.assertEqual(run()["final_payment_status"],"NOT_ASSIGNED")
    def test_11_no_certified_master(self):
        x=run()
        self.assertFalse(x["full_v251_v239_certified"])
        self.assertFalse(x["case23_full_method_coverage_certified"])
    def test_12_no_waterfall_auto_allocation(self):
        x=run()
        self.assertFalse(x["approved_waterfall_reservation_fully_integrated"])
        self.assertTrue(x["one_global_boundary_before_waterfall"])
    def test_13_cash_gap_does_not_assume_tds(self):
        x=run()
        self.assertEqual(x["shadow_cash_coverage_gap_not_receivable"],"20.00")
        self.assertFalse(x["tds_gst_credit_note_settlement_certified"])
    def test_14_zero_percent_cash_hypothesis_not_paid(self):
        x=run(payments=[bank(credit="1180.00")])
        self.assertEqual(x["shadow_reserved_cash_total"],"1180.00")
        self.assertEqual(x["real_bank_payments_reconciled"],0)
    def test_15_one_percent_cash_hypothesis(self):
        self.assertEqual(run(payments=[bank(credit="1170.00")])[
            "shadow_reserved_cash_total"],"1170.00")
    def test_16_three_percent_cash_hypothesis(self):
        self.assertEqual(run(payments=[bank(credit="1150.00")])[
            "shadow_reserved_cash_total"],"1150.00")
    def test_17_no_cross_upload_money(self):
        a=run(upload=A);b=run(upload=B)
        self.assertNotEqual(a["upload_id"],b["upload_id"])
        self.assertEqual(a["shadow_reserved_cash_total"],b["shadow_reserved_cash_total"])
        self.assertTrue(all(v[0]==A for v in a["scoped_shadow_edges"]))
        self.assertTrue(all(v[0]==B for v in b["scoped_shadow_edges"]))
    def test_18_dnm_without_explicit_mxp_provisional_only(self):
        x=run(payments=[bank(description="POSTAGE SEPTEMBER 2026")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertEqual(len(x["unreserved_dnm_candidates"]),1)
        self.assertEqual(x["unreserved_dnm_candidates"][0][-1],
                         "DNM_REVIEW_ONLY_NEVER_RESERVE")
    def test_19_ambiguous_dnm_no_reservation(self):
        iv=[invoice(),invoice(source_row=3,invoice_no="MXP10002")]
        x=run(invoices=iv,payments=[bank(description="POSTAGE SEPTEMBER 2026")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("DNM_AMBIGUOUS_RUNNER_UP",x["matrix_payment_holds"][0][2])
    def test_20_contradictory_mxp_references_do_not_allocate(self):
        x=run(payments=[bank(description="POSTAGE MXP10001 MXP10002 SEPTEMBER 2026")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("CONTRADICTORY_MULTIPLE_MXP_REFERENCES",
                      x["matrix_payment_holds"][0][2])
    def test_21_unknown_mxp_blocks_fallback(self):
        x=run(payments=[bank(description="POSTAGE MXP99999 SEPTEMBER 2026")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertEqual(x["unreserved_dnm_candidates"],())
    def test_22_nonmatching_period_held(self):
        x=run(payments=[bank(service_periods=("2026-08",))])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("SERVICE_PERIOD_CONFLICT",x["matrix_payment_holds"][0][2])
    def test_23_empty_service_evidence_held(self):
        x=run(payments=[bank(service_periods=())])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_24_future_invoice_not_allocated(self):
        x=run(invoices=[invoice(issue_date=date(2026,10,1))])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_25_absent_master_identity_holds(self):
        x=run(master=[("0002","SYNTHETIC BETA")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("SOL_CLIENT_NOT_IN_SELECTED_MASTER",x["matrix_payment_holds"][0][2])
    def test_26_synthetic_partial_proof_still_only_review(self):
        x=run(payments=[bank(credit="500.00")],
              relationships=[proof("PARTIAL")])
        self.assertEqual(x["review_edges_not_financial_allocations"][0][3],
                         "PARTIAL_REVIEW")
        self.assertEqual(x["real_bank_payments_reconciled"],0)
    def test_27_unconfirmed_partial_proof_holds(self):
        x=run(payments=[bank(credit="500.00")],
              relationships=[proof("PARTIAL",confirmed=False)])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_28_gst_later_with_synthetic_document_no_status(self):
        x=run(payments=[bank(credit="180.00",
              description="GST SEPTEMBER 2026 MXP10001")],
              relationships=[proof("GST")])
        self.assertEqual(x["shadow_reserved_cash_total"],"180.00")
        self.assertEqual(x["review_edges_not_financial_allocations"][0][3],
                         "GST_COMPONENT_REVIEW")
        self.assertEqual(x["real_bank_payments_reconciled"],0)
    def test_29_gst_later_missing_proof_holds(self):
        x=run(payments=[bank(credit="180.00",
              description="GST SEPTEMBER 2026 MXP10001")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("GST_LATER_APPROVAL_MISSING",x["matrix_payment_holds"][0][2])
    def test_30_sbisa_relationship_proof_review_only(self):
        x=run(invoices=[invoice(sol="")],
              payments=[bank(sol="1")],relationships=[proof("SBISA")])
        self.assertEqual(x["review_edges_not_financial_allocations"][0][3],
                         "SBISA_REVIEW")
        self.assertFalse(x["full_v251_v239_certified"])
    def test_31_sbisa_without_relationship_holds(self):
        x=run(invoices=[invoice(sol="")],payments=[bank(sol="1")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_32_cross_sol_proof_and_official_master_both_required(self):
        x=run(payments=[bank(sol="0002",client="SYNTHETIC BETA")],
              relationships=[proof("CROSS_SOL")])
        self.assertEqual(x["review_edges_not_financial_allocations"][0][3],
                         "CROSS_SOL_REVIEW")
    def test_33_cross_sol_without_official_bank_master_holds(self):
        x=run(master=[("0001","SYNTHETIC ALPHA")],
              payments=[bank(sol="0002",client="SYNTHETIC BETA")],
              relationships=[proof("CROSS_SOL")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("CROSS_SOL_OFFICIAL_MASTER_IDENTITY_NOT_VERIFIED",
                      x["matrix_payment_holds"][0][2])
    def test_34_cross_sol_without_document_holds(self):
        x=run(payments=[bank(sol="0002",client="SYNTHETIC BETA")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_35_compound_cross_sol_gst_holds(self):
        x=run(payments=[bank(sol="0002",client="SYNTHETIC BETA",
              credit="180.00",description="GST MXP10001 SEPTEMBER 2026")],
              relationships=[proof("CROSS_SOL"),proof("GST",evidence_id="SYN-PROOF-002")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertIn("COMPOUND_EXCEPTION_NEEDS_INDEPENDENT_PROOF",
                      x["matrix_payment_holds"][0][2])
    def test_36_competing_two_full_payments_one_invoice_group_held(self):
        pay=[bank(),bank(source_row=3,credit="1160.00")]
        x=run(payments=pay)
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
        self.assertEqual(x["global_competing_invoice_groups_held"],("MXP10001",))
        self.assertEqual(len(x["globally_held_review_edges"]),1)
        self.assertTrue(all(row[0]==A for row in x["matrix_payment_holds"]))
    def test_37_multiple_documented_partial_payments_no_overcommit(self):
        pay=[bank(credit="500.00"),bank(source_row=3,credit="660.00")]
        proofs=[proof("PARTIAL"),proof("PARTIAL",row=3,evidence_id="SYN-PROOF-002")]
        x=run(payments=pay,relationships=proofs)
        self.assertEqual(x["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(len(x["scoped_shadow_edges"]),2)
        self.assertEqual(x["real_bank_payments_reconciled"],0)
    def test_38_explicit_mxp_amount_mismatch_no_partial_proof_held(self):
        x=run(payments=[bank(credit="500.00")])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")
    def test_39_payment_sourced_cash_not_rounding_up(self):
        x=run()
        self.assertEqual(x["shadow_bank_rows"][0][2],"1160.00")
    def test_40_missing_global_checkpoint_never_possible(self):
        x=run()
        self.assertTrue(x["one_global_boundary_before_waterfall"])
    def test_41_invoice_and_bank_evidence_hash_deterministic(self):
        a=args();b=args()
        self.assertEqual(a["expected_matrix_evidence_digest"],
                         b["expected_matrix_evidence_digest"])
    def test_42_change_bank_narration_changes_evidence_digest(self):
        a=args();b=args(payments=[bank(description="CHANGED MXP10001")])
        self.assertNotEqual(a["expected_matrix_evidence_digest"],
                            b["expected_matrix_evidence_digest"])
    def test_43_change_invoice_period_changes_evidence_digest(self):
        a=args();b=args(invoices=[invoice(service_periods=("2026-08",))])
        self.assertNotEqual(a["expected_matrix_evidence_digest"],
                            b["expected_matrix_evidence_digest"])
    def test_44_change_relationship_confirmed_changes_evidence_digest(self):
        a=args(relationships=[proof(confirmed=True)])
        b=args(relationships=[proof(confirmed=False)])
        self.assertNotEqual(a["expected_matrix_evidence_digest"],
                            b["expected_matrix_evidence_digest"])
    def test_45_change_master_pairs_changes_evidence_digest(self):
        a=args()
        b=args(master=[("0001","SYNTHETIC WRONG")])
        self.assertNotEqual(a["expected_matrix_evidence_digest"],
                            b["expected_matrix_evidence_digest"])
    def test_46_stale_scope_digest_refused(self):
        d=args();d["expected_workbook_digest"]="0"*64
        self.refused("SCOPED_WORKBOOK_DIGEST_MISMATCH",input_override=d)
    def test_47_stale_evidence_digest_refused(self):
        d=args();d["expected_matrix_evidence_digest"]="0"*64
        self.refused("MATRIX_EVIDENCE_DIGEST_MISMATCH",input_override=d)
    def test_48_missing_hash_format_refused(self):
        d=args();d["expected_matrix_evidence_digest"]="bad"
        self.refused("TWO_EXACT_SHA256_MANIFESTS_REQUIRED",input_override=d)
    def test_49_finance_unlock_refused(self):
        d=args();d["financial_apply"]="ENABLED"
        self.refused("FINANCIAL_APPLY_LOCK_REQUIRED",input_override=d)
    def test_50_scoped_invoice_amount_mismatch_refused(self):
        d=args()
        bad=replace(d["workbook"],invoices=(replace(d["workbook"].invoices[0],
                             gross="1181.00"),))
        d["workbook"]=bad
        d["expected_workbook_digest"]=fresh_workbook_digest(bad)
        self.refused("INVOICE_ID_AMOUNT_OR_PROTECTION_MISMATCH",input_override=d)
    def test_51_scoped_bank_credit_mismatch_refused(self):
        d=args()
        bad=replace(d["workbook"],banks=(replace(d["workbook"].banks[0],
                             credit="1161.00"),))
        d["workbook"]=bad
        d["expected_workbook_digest"]=fresh_workbook_digest(bad)
        self.refused("BANK_CREDIT_OR_PROTECTION_MISMATCH",input_override=d)
    def test_52_scoped_invoice_protection_marker_mismatch_refused(self):
        d=args()
        bad=replace(d["workbook"],invoices=(replace(d["workbook"].invoices[0],
                             original_s=0),))
        d["workbook"]=bad
        d["expected_workbook_digest"]=fresh_workbook_digest(bad)
        self.refused("INVOICE_ID_AMOUNT_OR_PROTECTION_MISMATCH",input_override=d)
    def test_53_scoped_bank_protection_marker_mismatch_refused(self):
        d=args()
        bad=replace(d["workbook"],banks=(replace(d["workbook"].banks[0],
                             original_k="OK"),))
        d["workbook"]=bad
        d["expected_workbook_digest"]=fresh_workbook_digest(bad)
        self.refused("BANK_CREDIT_OR_PROTECTION_MISMATCH",input_override=d)
    def test_54_source_invoice_original_S_protected(self):
        d=args(invoices=[invoice(original_s=0)])
        self.refused("PROTECTED_INVOICE_S_NONBLANK",input_override=d)
    def test_55_source_bank_original_K_protected(self):
        d=args(payments=[bank(original_k="OK")])
        self.refused("PROTECTED_BANK_K_NONBLANK",input_override=d)
    def test_56_duplicate_matrix_invoice_no_refused(self):
        d=args(invoices=[invoice(),invoice(source_row=3)])
        self.refused("DUPLICATE_MATRIX_INVOICE_IDENTITY",input_override=d)
    def test_57_mismatched_matrix_payment_count_refused(self):
        d=args()
        d["payments"]=()
        d["expected_matrix_evidence_digest"]=gate.evidence_digest(
            d["invoices"],d["payments"],d["master_pairs"],d["relationship_proofs"],
        )
        self.refused("MASTER_MATRIX_SOURCE_POPULATION_MISMATCH",input_override=d)
    def test_58_mismatched_matrix_invoice_row_refused(self):
        d=args()
        d["invoices"]=(invoice(source_row=3),)
        d["expected_matrix_evidence_digest"]=gate.evidence_digest(
            d["invoices"],d["payments"],d["master_pairs"],d["relationship_proofs"],
        )
        self.refused("MATRIX_INVOICE_ROW_NOT_IN_SCOPED_WORKBOOK",input_override=d)
    def test_59_forged_matrix_paid_status_refused(self):
        d=args();real=gate.plan_review_only(list(d["invoices"]),list(d["payments"]),
            list(d["master_pairs"]),source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(real);bad["all_real_bank_statuses"]="OK"
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("UNAUTHORIZED_MATRIX_RELEASE_OR_SOURCE_CHANGE",
                         input_override=d)
    def test_60_forged_matrix_extra_proposal_credit_refused(self):
        d=args();real=gate.plan_review_only(list(d["invoices"]),list(d["payments"]),
            list(d["master_pairs"]),source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(real);bad["candidate_rows"]=((2,"MXP10001","999.00",
               "EXACT_MXP_TDS_REVIEW",2),)
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("MATRIX_CREDIT_DIFFERS_FROM_SOURCE",input_override=d)
    def test_61_forged_matrix_unknown_invoice_refused(self):
        d=args();real=gate.plan_review_only(list(d["invoices"]),list(d["payments"]),
            list(d["master_pairs"]),source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(real);bad["candidate_rows"]=((2,"MXP99999","1160.00",
               "EXACT_MXP_TDS_REVIEW",2),)
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("MATRIX_PROPOSAL_OUTSIDE_VERIFIED_SOURCE",input_override=d)
    def test_62_repeated_execution_deterministic_no_input_mutation(self):
        d=args();before=repr(d)
        a=gate.connect_master_matrix_review(**d)
        b=gate.connect_master_matrix_review(**d)
        self.assertEqual(a,b)
        self.assertEqual(repr(d),before)

    def test_63_review_priority_exact_mxp_before_documented_gst(self):
        iv=(invoice(),invoice(source_row=3,invoice_no="MXP10002"))
        bank_rows=(
            bank(credit="180.00",description="GST MXP10002 SEPTEMBER 2026"),
            bank(source_row=3,credit="1160.00",
                 description="MXP10001 SEPTEMBER 2026"),
        )
        g=proof("GST",row=2,invoice_no="MXP10002")
        x=run(invoices=iv,payments=bank_rows,relationships=[g])
        self.assertEqual(len(x["review_edges_not_financial_allocations"]),2)
        self.assertEqual(
            [v[3] for v in x["review_edges_not_financial_allocations"]],
            ["EXACT_MXP_REVIEW","GST_COMPONENT_REVIEW"])
        self.assertEqual(x["shadow_reserved_cash_total"],"1340.00")

    def test_64_forged_dnm_unknown_bank_row_refused(self):
        d=args(payments=[bank(description="POSTAGE SEPTEMBER 2026")])
        actual=gate.plan_review_only(
            list(d["invoices"]),list(d["payments"]),list(d["master_pairs"]),
            source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(actual)
        bad["candidate_rows"]=((999,"MXP10001","1160.00",
                "DNM01_PROVISIONAL_NO_RESERVATION",2),)
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("PROVISIONAL_DNM_OUTSIDE_VERIFIED_SOURCE",
                         input_override=d)

    def test_65_forged_dnm_amount_mismatch_refused(self):
        d=args(payments=[bank(description="POSTAGE SEPTEMBER 2026")])
        actual=gate.plan_review_only(
            list(d["invoices"]),list(d["payments"]),list(d["master_pairs"]),
            source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(actual)
        bad["candidate_rows"]=((2,"MXP10001","999.00",
                "DNM01_PROVISIONAL_NO_RESERVATION",2),)
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("PROVISIONAL_DNM_CREDIT_SOURCE_MISMATCH",
                         input_override=d)

    def test_66_forged_dnm_with_explicit_mxp_ref_refused(self):
        d=args()
        actual=gate.plan_review_only(
            list(d["invoices"]),list(d["payments"]),list(d["master_pairs"]),
            source_sha256=SHA,master_sha256=MASTER_SHA)
        bad=dict(actual)
        bad["candidate_rows"]=((2,"MXP10001","1160.00",
                "DNM01_PROVISIONAL_NO_RESERVATION",2),)
        with patch.object(gate,"plan_review_only",return_value=bad):
            self.refused("PROVISIONAL_DNM_CONTRADICTORY_MXP_REF",
                         input_override=d)


if __name__=="__main__":
    unittest.main()
