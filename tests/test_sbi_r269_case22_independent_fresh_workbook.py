"""R26.9 Case 2.2 — Option B isolated fresh workbook QA (synthetic only)."""
from dataclasses import replace
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r269_core_cash_ledger_dry_run import (
    GlobalAdjudicationBoundary, LedgerRefusal,
)
from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook, ScopedInvoice, ScopedBank, ScopedMatrixProposal,
    FreshBatchRefusal, fresh_workbook_digest, scoped_proposal_digest,
    run_independent_fresh_workbook, MODE, STAGE,
)

A = "UPLOAD-A-001"
B = "UPLOAD-B-002"
SOURCE = "a"*64
MASTER = "b"*64


def invoice(upload_id=A, **kw):
    return replace(ScopedInvoice(upload_id,"MXP10001",2,"1180.00"),**kw)


def payment(upload_id=A, **kw):
    return replace(ScopedBank(upload_id,"SYN-PAY-001",2,"1160.00"),**kw)


def candidate(upload_id=A, **kw):
    return replace(ScopedMatrixProposal(
        upload_id,"SYN-PAY-001","MXP10001","1160.00",
        "EXACT_MXP_REVIEW","SYN-EVIDENCE-001",
    ),**kw)


def workbook(upload_id=A, invoices=None, banks=None, **kw):
    return FreshWorkbook(
        upload_id=upload_id,
        source_sha256=SOURCE,
        master_sha256=MASTER,
        invoices=tuple([invoice(upload_id)] if invoices is None else invoices),
        banks=tuple([payment(upload_id)] if banks is None else banks),
        **kw,
    )


def run(wb=None, steps=None, **extra):
    wb = workbook() if wb is None else wb
    steps = tuple([candidate(wb.upload_id),GlobalAdjudicationBoundary()]
                  if steps is None else steps)
    return run_independent_fresh_workbook(
        wb,steps,expected_workbook_digest=fresh_workbook_digest(wb),
        expected_scoped_plan_digest=scoped_proposal_digest(steps),**extra,
    )


class FreshWorkbookIndependentLedgerQA(unittest.TestCase):
    def hold(self,reason, **kw):
        with self.assertRaisesRegex((FreshBatchRefusal,LedgerRefusal),reason):
            run(**kw)

    def test_01_one_fresh_workbook_core_cash(self):
        x=run()
        self.assertEqual(x["stage"],STAGE)
        self.assertEqual(x["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(x["shadow_cash_coverage_gap_not_receivable"],"20.00")

    def test_02_option_B_explicit(self):
        self.assertEqual(run()["upload_mode"],MODE)

    def test_03_previous_workbook_allocations_not_read(self):
        self.assertFalse(run()["previous_approved_allocations_imported"])

    def test_04_historical_bank_status_not_copied(self):
        self.assertFalse(run()["previous_payment_statuses_imported"])

    def test_05_not_cross_workbook_allocation(self):
        self.assertFalse(run()["cross_workbook_allocation_performed"])

    def test_06_case_1_historical_row_counts_not_mandatory(self):
        x=run()
        self.assertEqual(x["bank_rows_in_this_upload"],1)
        self.assertEqual(x["invoice_rows_in_this_upload"],1)

    def test_07_no_real_financial_apply(self):
        self.assertTrue(run()["financial_apply_locked"])

    def test_08_no_real_database_writes(self):
        self.assertEqual(run()["real_database_writes"],0)

    def test_09_no_final_paid_status(self):
        self.assertIsNone(run()["financial_status"])

    def test_10_no_full_engine_certification(self):
        self.assertFalse(run()["complete_master_v251_matrix_v239_certified"])

    def test_11_same_invoice_no_different_fresh_workbooks_allowed(self):
        ra=run(workbook(A))
        rb=run(workbook(B))
        self.assertEqual(ra["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(rb["shadow_reserved_cash_total"],"1160.00")
        self.assertNotEqual(ra["upload_id"],rb["upload_id"])

    def test_12_source_row_2_reused_between_workbooks_allowed(self):
        ra=run(workbook(A))
        rb=run(workbook(B))
        self.assertEqual(ra["shadow_invoice_cash_rows"][0][1],2)
        self.assertEqual(rb["shadow_invoice_cash_rows"][0][1],2)

    def test_13_same_bank_key_different_workbook_allowed(self):
        ra=run(workbook(A))
        rb=run(workbook(B))
        self.assertEqual(ra["shadow_bank_rows"][0][0],rb["shadow_bank_rows"][0][0])
        self.assertNotEqual(ra["upload_id"],rb["upload_id"])

    def test_14_two_uploads_have_distinct_batch_manifests(self):
        self.assertNotEqual(fresh_workbook_digest(workbook(A)),
                            fresh_workbook_digest(workbook(B)))

    def test_15_two_uploads_have_distinct_scoped_plan_digest(self):
        aa=(candidate(A),GlobalAdjudicationBoundary())
        bb=(candidate(B),GlobalAdjudicationBoundary())
        self.assertNotEqual(scoped_proposal_digest(aa),scoped_proposal_digest(bb))

    def test_16_reusing_prior_approved_ledger_rows_refused(self):
        self.hold("PREVIOUS_WORKBOOK_ALLOCATIONS_NOT_PERMITTED",
                  previous_allocations=(("OLD-UPLOAD","MXP10001","1160.00"),))

    def test_17_reusing_prior_payment_OK_refused(self):
        self.hold("HISTORICAL_PAYMENT_STATUSES_NOT_PERMITTED",
                  previous_payment_statuses=(("OLD-UPLOAD","SYN-PAY-001","OK"),))

    def test_18_prior_status_even_SUSPENSE_row_refused(self):
        self.hold("HISTORICAL_PAYMENT_STATUSES_NOT_PERMITTED",
                  previous_payment_statuses=(("OLD-UPLOAD","SYN-PAY-001","SUSPENSE"),))

    def test_19_foreign_invoice_tag_refused(self):
        s=workbook(A,invoices=[invoice(B)])
        with self.assertRaisesRegex(FreshBatchRefusal,"FOREIGN_INVOICE_UPLOAD_SCOPE"):
            fresh_workbook_digest(s)

    def test_20_foreign_bank_tag_refused(self):
        s=workbook(A,banks=[payment(B)])
        with self.assertRaisesRegex(FreshBatchRefusal,"FOREIGN_PAYMENT_UPLOAD_SCOPE"):
            fresh_workbook_digest(s)

    def test_21_foreign_matrix_tag_refused(self):
        self.hold("FOREIGN_MATRIX_PROPOSAL_UPLOAD_SCOPE",
                  steps=[candidate(B),GlobalAdjudicationBoundary()])

    def test_22_no_mixed_proposals_even_if_same_bank_key(self):
        self.hold("FOREIGN_MATRIX_PROPOSAL_UPLOAD_SCOPE",
                  steps=[candidate(A),candidate(B,invoice_no="MXP10002"),
                         GlobalAdjudicationBoundary()])

    def test_23_mismatched_source_hash_in_batch_digest_refused(self):
        current=workbook(A)
        changed=replace(current,source_sha256="c"*64)
        steps=(candidate(A),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_WORKBOOK_SNAPSHOT_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                changed,steps,
                expected_workbook_digest=fresh_workbook_digest(current),
                expected_scoped_plan_digest=scoped_proposal_digest(steps),
            )

    def test_24_mismatched_master_hash_in_batch_digest_refused(self):
        current=workbook(A)
        changed=replace(current,master_sha256="c"*64)
        steps=(candidate(A),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_WORKBOOK_SNAPSHOT_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                changed,steps,
                expected_workbook_digest=fresh_workbook_digest(current),
                expected_scoped_plan_digest=scoped_proposal_digest(steps),
            )

    def test_25_mutated_invoice_amount_against_pinned_digest_refused(self):
        current=workbook(A)
        changed=replace(current,invoices=(invoice(A,gross="1181.00"),))
        steps=(candidate(A),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_WORKBOOK_SNAPSHOT_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                changed,steps,
                expected_workbook_digest=fresh_workbook_digest(current),
                expected_scoped_plan_digest=scoped_proposal_digest(steps),
            )

    def test_26_mutated_payment_amount_against_pinned_digest_refused(self):
        current=workbook(A)
        changed=replace(current,banks=(payment(A,credit="1160.01"),))
        steps=(candidate(A),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_WORKBOOK_SNAPSHOT_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                changed,steps,
                expected_workbook_digest=fresh_workbook_digest(current),
                expected_scoped_plan_digest=scoped_proposal_digest(steps),
            )

    def test_27_matrix_amount_changed_after_plan_pin_refused(self):
        wb=workbook(A)
        good=(candidate(A),GlobalAdjudicationBoundary())
        bad=(candidate(A,portion="1000.00"),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_MATRIX_PLAN_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                wb,bad,expected_workbook_digest=fresh_workbook_digest(wb),
                expected_scoped_plan_digest=scoped_proposal_digest(good),
            )

    def test_28_matrix_evidence_changed_after_plan_pin_refused(self):
        wb=workbook(A)
        good=(candidate(A),GlobalAdjudicationBoundary())
        bad=(candidate(A,evidence_ref="SYN-FORGED"),GlobalAdjudicationBoundary())
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_MATRIX_PLAN_DIGEST_MISMATCH"):
            run_independent_fresh_workbook(
                wb,bad,expected_workbook_digest=fresh_workbook_digest(wb),
                expected_scoped_plan_digest=scoped_proposal_digest(good),
            )

    def test_29_invalid_upload_id_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"EXPLICIT_VALID_FRESH_UPLOAD_ID_REQUIRED"):
            fresh_workbook_digest(workbook("BAD SPACE"))

    def test_30_short_upload_id_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"EXPLICIT_VALID_FRESH_UPLOAD_ID_REQUIRED"):
            fresh_workbook_digest(workbook("A"))

    def test_31_wrong_mode_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"INDEPENDENT_FRESH_WORKBOOK_MODE_REQUIRED"):
            fresh_workbook_digest(workbook(A,mode="IMPORT_PREVIOUS_LEDGER"))

    def test_32_source_SHA_malformed_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"EXPLICIT_SOURCE_AND_MASTER_SHA256_REQUIRED"):
            fresh_workbook_digest(replace(workbook(A),source_sha256="short"))

    def test_33_master_SHA_malformed_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"EXPLICIT_SOURCE_AND_MASTER_SHA256_REQUIRED"):
            fresh_workbook_digest(replace(workbook(A),master_sha256="short"))

    def test_34_invoices_must_be_immutable_tuple(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_RECORD_TUPLE_REQUIRED"):
            fresh_workbook_digest(replace(workbook(A),invoices=[invoice(A)]))

    def test_35_banks_must_be_immutable_tuple(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"FRESH_RECORD_TUPLE_REQUIRED"):
            fresh_workbook_digest(replace(workbook(A),banks=[payment(A)]))

    def test_36_plan_must_be_immutable_tuple(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"SCOPED_MATRIX_PLAN_TUPLE_REQUIRED"):
            run_independent_fresh_workbook(
                workbook(A),[candidate(A),GlobalAdjudicationBoundary()],
                expected_workbook_digest=fresh_workbook_digest(workbook(A)),
                expected_scoped_plan_digest="a"*64,
            )

    def test_37_unknown_plan_step_refused(self):
        with self.assertRaisesRegex(FreshBatchRefusal,"FOREIGN_OR_UNKNOWN_MATRIX_STEP"):
            scoped_proposal_digest((candidate(A),object(),GlobalAdjudicationBoundary()))

    def test_38_duplicate_invoice_id_within_one_workbook_refused(self):
        self.hold("DUPLICATE_INVOICE_IDENTITY",
                  wb=workbook(A,invoices=[invoice(A),invoice(A,source_row=3)]))

    def test_39_duplicate_bank_key_within_one_workbook_refused(self):
        self.hold("DUPLICATE_BANK_IDENTITY",
                  wb=workbook(A,banks=[payment(A),payment(A,source_row=3)]))

    def test_40_duplicate_source_invoice_row_within_one_workbook_refused(self):
        self.hold("DUPLICATE_INVOICE_IDENTITY",
                  wb=workbook(A,invoices=[
                      invoice(A),invoice(A,invoice_no="MXP10002"),
                  ]))

    def test_41_duplicate_source_bank_row_within_one_workbook_refused(self):
        self.hold("DUPLICATE_BANK_IDENTITY",
                  wb=workbook(A,banks=[
                      payment(A),payment(A,bank_key="SYN-PAY-002"),
                  ]))

    def test_42_protected_invoice_S_in_current_fresh_upload_still_blocks(self):
        self.hold("PROTECTED_INVOICE_S_NONBLANK",
                  wb=workbook(A,invoices=[invoice(A,original_s=0)]))

    def test_43_protected_bank_K_in_current_fresh_upload_still_blocks(self):
        self.hold("PROTECTED_BANK_K_NONBLANK",
                  wb=workbook(A,banks=[payment(A,original_k="OK")]))

    def test_44_double_bank_spend_within_workbook_refused(self):
        wb=workbook(A,invoices=[
            invoice(A,gross="1000.00"),
            invoice(A,invoice_no="MXP10002",source_row=3,gross="900.00")
        ])
        steps=[candidate(A,invoice_no="MXP10001",portion="1000.00"),
               candidate(A,invoice_no="MXP10002",portion="500.00",
                         evidence_ref="SYN-EVIDENCE-002"),GlobalAdjudicationBoundary()]
        self.hold("BANK_CREDIT_CAPACITY_EXCEEDED",wb=wb,steps=steps)

    def test_45_overinvoice_even_if_credit_available_refused(self):
        wb=workbook(A,banks=[payment(A,credit="1300.00")])
        self.hold("INVOICE_CASH_CAPACITY_EXCEEDED",wb=wb,
                  steps=[candidate(A,portion="1300.00"),GlobalAdjudicationBoundary()])

    def test_46_no_waterfall_before_global_checkpoint(self):
        self.hold("WATERFALL_BEFORE_GLOBAL_ADJUDICATION",
                  steps=[candidate(A,method="WATERFALL_REVIEW"),
                         GlobalAdjudicationBoundary()])

    def test_47_provisional_DNM_does_not_reserve_cash(self):
        self.hold("PROVISIONAL_DNM_CANNOT_RESERVE_CASH",
                  steps=[candidate(A,method="DNM_PROVISIONAL"),
                         GlobalAdjudicationBoundary()])

    def test_48_missing_global_checkpoint_refused(self):
        self.hold("GLOBAL_ADJUDICATION_BOUNDARY_REQUIRED",steps=[candidate(A)])

    def test_49_one_bank_credit_two_invoice_partials_within_batch(self):
        wb=workbook(A,
            invoices=(invoice(A,gross="600.00"),
                      invoice(A,source_row=3,invoice_no="MXP10002",gross="800.00")),
            banks=(payment(A,credit="1160.00"),))
        steps=[candidate(A,portion="600.00",method="PARTIAL_REVIEW"),
               candidate(A,invoice_no="MXP10002",portion="560.00",
                         method="PARTIAL_REVIEW",evidence_ref="SYN-EVIDENCE-002"),
               GlobalAdjudicationBoundary()]
        x=run(wb=wb,steps=steps)
        self.assertEqual(x["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(x["shadow_cash_coverage_gap_not_receivable"],"240.00")
        self.assertEqual(len(x["shadow_edges"]),2)

    def test_50_two_bank_credits_one_invoice_within_batch(self):
        wb=workbook(A,
            banks=(payment(A,credit="500.00"),
                   payment(A,bank_key="SYN-PAY-002",source_row=3,credit="680.00")))
        steps=[
            candidate(A,portion="500.00",method="PARTIAL_REVIEW"),
            candidate(A,bank_key="SYN-PAY-002",portion="680.00",
                      method="PARTIAL_REVIEW",evidence_ref="SYN-EVIDENCE-002"),
            GlobalAdjudicationBoundary(),
        ]
        x=run(wb=wb,steps=steps)
        self.assertEqual(x["shadow_cash_coverage_gap_not_receivable"],"0.00")
        self.assertEqual(x["shadow_reserved_cash_total"],"1180.00")

    def test_51_caller_inputs_not_mutated(self):
        wb=workbook(A)
        steps=(candidate(A),GlobalAdjudicationBoundary())
        before=repr((wb,steps))
        run(wb=wb,steps=steps)
        self.assertEqual(before,repr((wb,steps)))

    def test_52_rerun_same_upload_same_cash_and_digest(self):
        wb=workbook(A)
        x=run(wb=wb)
        y=run(wb=wb)
        self.assertEqual(x,y)

    def test_53_reused_source_bytes_under_new_upload_id_allow_dry_run_only(self):
        x=run(wb=workbook(A))
        y=run(wb=workbook(B))
        self.assertEqual(x["shadow_reserved_cash_total"],y["shadow_reserved_cash_total"])
        self.assertFalse(x["cross_upload_transaction_duplicate_detection_completed"])
        self.assertFalse(y["cross_upload_transaction_duplicate_detection_completed"])
        self.assertFalse(x["production_release_authorized"])

    def test_54_source_xlsx_bytes_not_attested_by_core(self):
        self.assertFalse(run()["source_xlsx_sha_validated_at_this_layer"])

    def test_55_no_bank_event_provenance_claim_from_scope_binding(self):
        self.assertFalse(run()["finance_approved_balance_or_utr_confirmed"])

    def test_56_empty_fresh_workbook_with_boundary(self):
        wb=workbook(A,invoices=(),banks=())
        x=run(wb=wb,steps=[GlobalAdjudicationBoundary()])
        self.assertEqual(x["shadow_reserved_cash_total"],"0.00")

    def test_57_no_cross_upload_balance_in_first_result(self):
        first=run(wb=workbook(A))
        second=run(wb=workbook(B,banks=[payment(B,credit="900.00")],
                               invoices=[invoice(B,gross="900.00")]),
                   steps=[candidate(B,portion="900.00"),GlobalAdjudicationBoundary()])
        self.assertEqual(first["shadow_reserved_cash_total"],"1160.00")
        self.assertEqual(second["shadow_reserved_cash_total"],"900.00")
        self.assertEqual(first["shadow_cash_coverage_gap_not_receivable"],"20.00")
        self.assertEqual(second["shadow_cash_coverage_gap_not_receivable"],"0.00")

    def test_58_result_does_not_enable_historical_status_copy(self):
        x=run()
        self.assertFalse(x["historical_workbooks_read"])
        self.assertFalse(x["previous_payment_statuses_imported"])
        self.assertIsNone(x["financial_status"])


    def test_59_all_shadow_edge_receipts_contain_upload_scope(self):
        a=run(wb=workbook(A))
        b=run(wb=workbook(B))
        self.assertEqual(a["scoped_shadow_edges"][0][0],A)
        self.assertEqual(b["scoped_shadow_edges"][0][0],B)
        self.assertNotEqual(a["scoped_shadow_edges"],b["scoped_shadow_edges"])

    def test_60_all_bank_balance_rows_contain_upload_scope(self):
        a=run(wb=workbook(A))
        b=run(wb=workbook(B))
        self.assertEqual(a["scoped_shadow_bank_rows"][0][0],A)
        self.assertEqual(b["scoped_shadow_bank_rows"][0][0],B)

    def test_61_all_invoice_cash_gap_rows_contain_upload_scope(self):
        a=run(wb=workbook(A))
        b=run(wb=workbook(B))
        self.assertEqual(a["scoped_shadow_invoice_cash_rows"][0][0],A)
        self.assertEqual(b["scoped_shadow_invoice_cash_rows"][0][0],B)

    def test_62_no_scope_rows_derived_from_older_upload(self):
        a=run(wb=workbook(A))
        self.assertTrue(all(row[0]==A for row in a["scoped_shadow_edges"]))
        self.assertTrue(all(row[0]==A for row in a["scoped_shadow_bank_rows"]))
        self.assertTrue(all(row[0]==A for row in a["scoped_shadow_invoice_cash_rows"]))


if __name__ == "__main__":
    unittest.main()
