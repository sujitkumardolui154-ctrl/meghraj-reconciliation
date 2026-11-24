"""R26.4 synthetic accounting QA; NEVER real SBI invoices or financial Apply."""
import sys
import unittest
from dataclasses import replace
from datetime import date
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
from sbi_r26_independent_financial_oracle import Invoice, Payment, R26Refusal
from sbi_r262_rebuild_candidate_planner import fixture_digest, RebuildRefusal
from sbi_r263_global_allocation_shadow import (
    Proposal, SyntheticProof, GlobalGate, proposal_digest, R263Refusal,
)
from sbi_r264_financial_accounting_shadow import (
    SyntheticTDS, SyntheticCreditNote, accounting_digest,
    account_synthetic_only, R264Refusal, STAGE,
)

MASTER = (("0001","SYNTHETIC ALPHA"),
          ("0002","SYNTHETIC BETA"),
          ("1","SYNTHETIC ALPHA"))

def inv(**kw):
    x=Invoice("SYN-MXP-001","0001","SYNTHETIC ALPHA","1000.00",
              "90.00","90.00","1180.00","1180.00",
              date(2026,9,1),("2026-09",))
    return replace(x,**kw)

def pay(**kw):
    x=Payment("SYN-PAY-001","0001","SYNTHETIC ALPHA","1160.00",
              date(2026,9,15),("2026-09",),("SYN-MXP-001",))
    return replace(x,**kw)

def prop(**kw):
    return replace(Proposal("SYN-PAY-001","SYN-MXP-001","1160.00"),**kw)

def proof(kind="PARTIAL",key="SYN-PROOF-001",payment_key="SYN-PAY-001",
          invoice_key="SYN-MXP-001",authority="SYNTHETIC_QA_ONLY"):
    return SyntheticProof(key,kind,payment_key,invoice_key,authority)

def tds(**kw):
    return replace(SyntheticTDS("SYN-TDS-001","SYN-PAY-001",
                               "SYN-MXP-001",2,"20.00"),**kw)

def note(**kw):
    return replace(SyntheticCreditNote("SYN-CN-001","SYN-MXP-001",
                                      "20.00",date(2026,9,16)),**kw)

def run(invoices=None,payments=None,steps=None,proofs=(),tds_evidence=(),
        credit_notes=(),master=MASTER,**extra):
    invoices=[inv()] if invoices is None else list(invoices)
    payments=[pay()] if payments is None else list(payments)
    steps=[prop(),GlobalGate()] if steps is None else list(steps)
    proofs=list(proofs)
    tds_evidence=list(tds_evidence)
    credit_notes=list(credit_notes)
    return account_synthetic_only(
        invoices,payments,list(master),steps,proofs,tds_evidence,credit_notes,
        expected_fixture_sha256=fixture_digest(invoices,payments,list(master)),
        expected_plan_sha256=proposal_digest(steps,proofs),
        expected_accounting_sha256=accounting_digest(tds_evidence,credit_notes),
        **extra,
    )

def partial_steps(*payment_amounts):
    steps=[]
    proofs=[]
    for i,credit in enumerate(payment_amounts,1):
        p=f"SYN-PAY-{i:03d}"
        k=f"SYN-PROOF-{i:03d}"
        steps.append(Proposal(p,"SYN-MXP-001",credit,"PARTIAL_REVIEW",k))
        proofs.append(proof(key=k,payment_key=p))
    steps.append(GlobalGate())
    return steps,proofs


class R264SyntheticFinancialAccountingTests(unittest.TestCase):
    def test_01_cash_only_1160_does_not_create_tds(self):
        x=run()
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"],
            (("SYN-MXP-001","1180.00","1160.00","0.00","0.00","20.00"),))
        self.assertEqual(x["illustrative_tds_total"],"0.00")
        self.assertIsNone(x["financial_status"])

    def test_02_explicit_tds20_synthetic_evidence_zero_illustrative_gap(self):
        x=run(tds_evidence=[tds()])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"0.00")
        self.assertEqual(x["illustrative_tds_total"],"20.00")
        self.assertFalse(x["full_master_v251_matrix_v239_certified"])

    def test_03_tds_0_percent_synthetic_case(self):
        x=run(payments=[pay(credit="1180.00")],
              steps=[prop(credit_portion="1180.00"),GlobalGate()],
              tds_evidence=[tds(rate_percent=0,withholding="0.00")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"0.00")

    def test_04_tds_1_percent(self):
        x=run(payments=[pay(credit="1170.00")],
              steps=[prop(credit_portion="1170.00"),GlobalGate()],
              tds_evidence=[tds(rate_percent=1,withholding="10.00")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_tds_total"],"10.00")

    def test_05_tds_3_percent(self):
        x=run(payments=[pay(credit="1150.00")],
              steps=[prop(credit_portion="1150.00"),GlobalGate()],
              tds_evidence=[tds(rate_percent=3,withholding="30.00")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_tds_total"],"30.00")

    def test_06_tds_3_percent_half_up_3_165_to_3_17(self):
        i=inv(taxable="105.50",cgst="6.25",sgst="6.25",
              gross="118.00",outstanding="118.00")
        p=pay(credit="114.83")
        x=run(invoices=[i],payments=[p],
              steps=[prop(credit_portion="114.83"),GlobalGate()],
              tds_evidence=[tds(rate_percent=3,withholding="3.17")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_tds_total"],"3.17")

    def test_07_wrong_tds_amount_hold(self):
        x=run(tds_evidence=[tds(withholding="19.99")])
        self.assertIn("TDS_AMOUNT_OR_HALF_UP_RATE_MISMATCH",x["blocker_codes"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"],())

    def test_08_tds_rate_4_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_TDS_EVIDENCE_REFUSED"):
            run(tds_evidence=[tds(rate_percent=4,withholding="40.00")])

    def test_09_tds_rate_boolean_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_TDS_EVIDENCE_REFUSED"):
            run(tds_evidence=[tds(rate_percent=True,withholding="10.00")])

    def test_10_real_tds_authority_claim_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_TDS_EVIDENCE_REFUSED"):
            run(tds_evidence=[tds(authority="SIGNED_FINANCE_APPROVAL")])

    def test_11_non_synthetic_tds_key_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_TDS_EVIDENCE_REFUSED"):
            run(tds_evidence=[tds(key="REAL-TDS-1")])

    def test_12_duplicate_tds_evidence_key_held(self):
        x=run(tds_evidence=[tds(),tds()])
        self.assertIn("DUPLICATE_TDS_EVIDENCE_KEY",x["blocker_codes"])

    def test_13_multiple_tds_withholdings_same_invoice_held(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="560.00")
        steps,proofs=partial_steps("600.00","560.00")
        x=run(payments=[p1,p2],steps=steps,proofs=proofs,tds_evidence=[
            tds(rate_percent=2,withholding="20.00"),
            tds(key="SYN-TDS-002",payment_key="SYN-PAY-002",
                rate_percent=2,withholding="20.00")
        ])
        self.assertIn("TDS_CLAIMED_MORE_THAN_ONCE_PER_INVOICE",x["blocker_codes"])

    def test_14_tds_without_any_cash_edge_held(self):
        x=run(steps=[GlobalGate()],tds_evidence=[tds()])
        self.assertIn("TDS_WITHOUT_CASH_RESERVATION",x["blocker_codes"])

    def test_15_tds_linked_only_to_waterfall_is_held(self):
        p=pay(mxp_refs=())
        steps=[GlobalGate(),prop(kind="WATERFALL",
                                 proof_key="SYN-PROOF-001")]
        x=run(payments=[p],steps=steps,proofs=[proof("WATERFALL")],
              tds_evidence=[tds()])
        self.assertIn("TDS_REQUIRES_STANDARD_OR_PARTIAL_METHOD",x["blocker_codes"])
        self.assertIn("TDS_REQUIRES_EXACT_INVOICE_REFERENCE",x["blocker_codes"])

    def test_16_credit_note_20_reduces_illustrative_gap(self):
        x=run(credit_notes=[note()])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_credit_note_total"],"20.00")
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"0.00")

    def test_17_credit_note_10_leaves_10_gap(self):
        x=run(credit_notes=[note(credit_gross="10.00")])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"10.00")

    def test_18_duplicate_credit_note_id_held(self):
        x=run(credit_notes=[note(),note()])
        self.assertIn("DUPLICATE_CREDIT_NOTE_KEY",x["blocker_codes"])

    def test_19_negative_credit_note_held(self):
        x=run(credit_notes=[note(credit_gross="-1.00")])
        self.assertIn("CREDIT_NOTE_NONPOSITIVE",x["blocker_codes"])

    def test_20_zero_credit_note_held(self):
        x=run(credit_notes=[note(credit_gross="0.00")])
        self.assertIn("CREDIT_NOTE_NONPOSITIVE",x["blocker_codes"])

    def test_21_credit_note_before_invoice_issue_held(self):
        x=run(credit_notes=[note(issue_date=date(2026,8,31))])
        self.assertIn("CREDIT_NOTE_BEFORE_INVOICE_ISSUE",x["blocker_codes"])

    def test_22_real_credit_note_approval_flag_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_CREDIT_NOTE_EVIDENCE_REFUSED"):
            run(credit_notes=[note(authority="REAL_APPROVED")])

    def test_23_missing_credit_note_invoice_link_held(self):
        x=run(credit_notes=[note(invoice_key="SYN-MXP-999")])
        self.assertIn("CREDIT_NOTE_UNLINKED_TO_SYNTHETIC_INVOICE",x["blocker_codes"])

    def test_24_credit_note_exceeds_original_gross_held(self):
        x=run(credit_notes=[note(credit_gross="1180.01")])
        self.assertIn("CREDIT_NOTE_EXCEEDS_INVOICE_GROSS",x["blocker_codes"])

    def test_25_cash_plus_tds_plus_credit_note_over_settlement_held(self):
        x=run(tds_evidence=[tds()],credit_notes=[note()])
        self.assertIn("GROSS_CASH_TDS_CN_OVERSETTLEMENT",x["blocker_codes"])
        self.assertFalse(x["accounting_candidate_pass"])

    def test_26_partial_500_plus_credit_note_680_illustrative(self):
        p=pay(credit="500.00")
        steps,proofs=partial_steps("500.00")
        x=run(payments=[p],steps=steps,proofs=proofs,
              credit_notes=[note(credit_gross="680.00")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"0.00")

    def test_27_gst_component_cash_180_illustrative(self):
        p=pay(credit="180.00",gst_narration=True)
        x=run(payments=[p],steps=[
            prop(kind="GST_REVIEW",credit_portion="180.00",
                 proof_key="SYN-PROOF-001"),GlobalGate()],
            proofs=[proof("GST")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_gst_component_cash_total"],"180.00")
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"1000.00")

    def test_28_repeated_gst_only_credit_over_180_cap(self):
        p1=pay(credit="180.00",gst_narration=True)
        p2=pay(key="SYN-PAY-002",credit="180.00",gst_narration=True)
        steps=[prop(kind="GST_REVIEW",credit_portion="180.00",
                    proof_key="SYN-PROOF-001"),
               prop(payment_key="SYN-PAY-002",kind="GST_REVIEW",
                    credit_portion="180.00",proof_key="SYN-PROOF-002"),
               GlobalGate()]
        proofs=[proof("GST"),proof("GST",key="SYN-PROOF-002",payment_key="SYN-PAY-002")]
        x=run(payments=[p1,p2],steps=steps,proofs=proofs)
        self.assertIn("GST_COMPONENT_EXCEEDS_INVOICE_TAX",x["blocker_codes"])

    def test_29_single_gst_cash_above_original_tax_held_by_r263(self):
        p=pay(credit="200.00",gst_narration=True)
        x=run(payments=[p],steps=[
            prop(credit_portion="200.00",kind="GST_REVIEW",
                 proof_key="SYN-PROOF-001"),GlobalGate()],
            proofs=[proof("GST")])
        self.assertIn("R263_GLOBAL_LEDGER_BLOCKED",x["blocker_codes"])

    def test_30_missing_gst_proof_is_not_auto_accepted(self):
        p=pay(credit="180.00",gst_narration=True)
        x=run(payments=[p],steps=[
            prop(credit_portion="180.00",kind="GST_REVIEW"),GlobalGate()])
        self.assertIn("GST_COMPONENT_DOCUMENTARY_PROOF_REQUIRED",x["blocker_codes"])

    def test_31_gst_narration_standard_method_is_held(self):
        x=run(payments=[pay(gst_narration=True)])
        self.assertIn("GST_NARRATION_MUST_BE_SEPARATELY_ADJUDICATED",x["blocker_codes"])

    def test_32_two_partial_bank_credits_do_not_overallocate(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="580.00")
        steps,proofs=partial_steps("600.00","580.00")
        x=run(payments=[p1,p2],steps=steps,proofs=proofs)
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"0.00")
        self.assertEqual(len(x["synthetic_payment_unassigned_rows"]),2)

    def test_33_two_partials_over_1180_hold(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="600.00")
        steps,proofs=partial_steps("600.00","600.00")
        x=run(payments=[p1,p2],steps=steps,proofs=proofs)
        self.assertIn("SHADOW_INVOICE_OUTSTANDING_OVERALLOCATED",x["blocker_codes"])

    def test_34_waterfall_after_gate_two_invoice_cash_split(self):
        i1=inv(taxable="500.00",cgst="45.00",sgst="45.00",
               gross="590.00",outstanding="590.00")
        i2=replace(i1,key="SYN-MXP-002")
        p=pay(credit="1000.00",mxp_refs=())
        steps=[GlobalGate(),
               prop(kind="WATERFALL",credit_portion="590.00",
                    proof_key="SYN-PROOF-001"),
               prop(invoice_key="SYN-MXP-002",kind="WATERFALL",
                    credit_portion="410.00",proof_key="SYN-PROOF-002")]
        proofs=[proof("WATERFALL"),
                proof("WATERFALL",key="SYN-PROOF-002",invoice_key="SYN-MXP-002")]
        x=run(invoices=[i1,i2],payments=[p],steps=steps,proofs=proofs)
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(tuple(row[-1] for row in x["synthetic_invoice_illustrative_rows"]),
                         ("0.00","180.00"))
        self.assertEqual(x["synthetic_payment_unassigned_rows"][0][-1],"0.00")

    def test_35_waterfall_before_gate_is_held(self):
        x=run(payments=[pay(mxp_refs=())],
              steps=[prop(kind="WATERFALL",proof_key="SYN-PROOF-001"),
                     GlobalGate()],
              proofs=[proof("WATERFALL")])
        self.assertIn("WATERFALL_BEFORE_GLOBAL_GATE",x["blocker_codes"])

    def test_36_earlier_matching_after_gate_is_held(self):
        x=run(steps=[GlobalGate(),prop()])
        self.assertIn("EARLIER_MATCHING_AFTER_GLOBAL_GATE",x["blocker_codes"])

    def test_37_dnm_candidate_does_not_account_cash(self):
        x=run(payments=[pay(mxp_refs=())],
              steps=[prop(kind="DNM_REVIEW"),GlobalGate()])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_cash_total"],"0.00")
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"1180.00")
        self.assertEqual(x["synthetic_payment_unassigned_rows"][0][-1],"1160.00")

    def test_38_duplicate_source_invoice_no_fails_closed(self):
        with self.assertRaisesRegex(R264Refusal,"SOURCE_DUPLICATE_IDENTITIES_REFUSED"):
            run(invoices=[inv(),inv()])

    def test_39_duplicate_bank_payment_key_fails_closed(self):
        with self.assertRaisesRegex(R264Refusal,"SOURCE_DUPLICATE_IDENTITIES_REFUSED"):
            run(payments=[pay(),pay()])

    def test_40_duplicate_same_pair_r263_atomic_reject(self):
        x=run(steps=[prop(),prop(),GlobalGate()])
        self.assertIn("REPEATED_PAYMENT_INVOICE_EDGE",x["blocker_codes"])
        self.assertEqual(x["synthetic_payment_unassigned_rows"],())

    def test_41_wrong_evidence_sha_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"ACCOUNTING_EVIDENCE_SHA256_MISMATCH"):
            a=[inv()];b=[pay()];s=[prop(),GlobalGate()]
            account_synthetic_only(a,b,MASTER,s,
                expected_fixture_sha256=fixture_digest(a,b,MASTER),
                expected_plan_sha256=proposal_digest(s,()),
                expected_accounting_sha256="0"*64)

    def test_42_missing_evidence_sha_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"EXPLICIT_ACCOUNTING_SHA256_REQUIRED"):
            a=[inv()];b=[pay()];s=[prop(),GlobalGate()]
            account_synthetic_only(a,b,MASTER,s,
                expected_fixture_sha256=fixture_digest(a,b,MASTER),
                expected_plan_sha256=proposal_digest(s,()),
                expected_accounting_sha256="bad")

    def test_43_unlock_financial_apply_rejected(self):
        with self.assertRaisesRegex(R264Refusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            run(financial_apply="ENABLED")

    def test_44_real_invoice_id_not_accepted(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_INVOICE_REQUIRED"):
            run(invoices=[inv(key="MXP19970")])

    def test_45_numeric_source_master_sol_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"SYNTHETIC_MASTER_ONLY"):
            run(master=((1,"SYNTHETIC ALPHA"),))

    def test_46_invoice_S_0_protected(self):
        x=run(invoices=[inv(source_s_marker=0)])
        self.assertIn("ORIGINAL_K_OR_S_PROTECTED",x["blocker_codes"])

    def test_47_payment_K_historical_marker_protected(self):
        x=run(payments=[pay(original_k="OK")])
        self.assertIn("ORIGINAL_K_OR_S_PROTECTED",x["blocker_codes"])

    def test_48_unknown_master_identity_blocks_match(self):
        x=run(master=(("0002","SYNTHETIC BETA"),))
        self.assertIn("SAME_SOL_OFFICIAL_IDENTITY_NOT_VERIFIED",x["blocker_codes"])

    def test_49_nonpositive_bank_credit_no_status(self):
        x=run(payments=[pay(credit="-1.00")],steps=[GlobalGate()])
        self.assertIn("NONPOSITIVE_BANK_CREDIT_REFUSED",x["blocker_codes"])
        self.assertIsNone(x["financial_status"])

    def test_50_subcent_credit_note_value_refused(self):
        with self.assertRaisesRegex(R26Refusal,"NONFINITE_OR_SUBCENT_MONEY"):
            run(credit_notes=[note(credit_gross="1.001")])

    def test_51_two_distinct_credit_notes_same_invoice_aggregate(self):
        x=run(credit_notes=[note(credit_gross="5.00"),
                            note(key="SYN-CN-002",credit_gross="5.00")])
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["illustrative_credit_note_total"],"10.00")
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"10.00")

    def test_52_credit_note_unsupported_date_type_refused(self):
        with self.assertRaisesRegex(R264Refusal,"INVALID_OR_REAL_CREDIT_NOTE_EVIDENCE_REFUSED"):
            run(credit_notes=[note(issue_date="2026-09-16")])

    def test_53_no_financial_status_or_duplicate_label_created(self):
        x=run(tds_evidence=[tds()])
        self.assertIsNone(x["financial_status"])
        self.assertTrue(x["no_actual_payment_or_duplicate_status_classified"])
        self.assertFalse(x["real_v218_financial_writer_amount_parity_verified"])
        self.assertFalse(x["real_53_column_report_financial_parity_verified"])

    def test_54_wrong_source_fixture_sha_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"FIXTURE_SHA256_MISMATCH"):
            a=[inv()];b=[pay()];s=[prop(),GlobalGate()]
            account_synthetic_only(a,b,MASTER,s,
                expected_fixture_sha256="0"*64,
                expected_plan_sha256=proposal_digest(s,()),
                expected_accounting_sha256=accounting_digest((),()))

    def test_55_wrong_plan_sha_refused(self):
        with self.assertRaisesRegex(R263Refusal,"PLAN_SHA256_MISMATCH"):
            a=[inv()];b=[pay()];s=[prop(),GlobalGate()]
            account_synthetic_only(a,b,MASTER,s,
                expected_fixture_sha256=fixture_digest(a,b,MASTER),
                expected_plan_sha256="0"*64,
                expected_accounting_sha256=accounting_digest((),()))

    def test_56_credit_note_on_protected_invoice_even_without_bank_edge(self):
        x=run(invoices=[inv(source_s_marker=0)],steps=[GlobalGate()],
              credit_notes=[note()])
        self.assertIn("CREDIT_NOTE_AGAINST_PROTECTED_INVOICE",x["blocker_codes"])

    def test_57_tds_underlying_r263_ref_mismatch_holds_batch(self):
        x=run(payments=[pay(mxp_refs=("SYN-MXP-999",))],tds_evidence=[tds()])
        self.assertIn("CONTRADICTORY_MXP_REFERENCE",x["blocker_codes"])

    def test_58_cash_is_not_inferred_as_withheld_tax(self):
        a=run()
        b=run(tds_evidence=[tds()])
        self.assertEqual(a["illustrative_cash_total"],b["illustrative_cash_total"])
        self.assertEqual(a["illustrative_tds_total"],"0.00")
        self.assertEqual(b["illustrative_tds_total"],"20.00")

    def test_59_unassigned_payment_cash_conserved(self):
        p=pay(credit="1180.00")
        steps,proofs=partial_steps("600.00")
        x=run(payments=[p],steps=steps,proofs=proofs)
        self.assertTrue(x["accounting_candidate_pass"])
        self.assertEqual(x["synthetic_payment_unassigned_rows"][0][-1],"580.00")
        self.assertEqual(x["synthetic_invoice_illustrative_rows"][0][-1],"580.00")

    def test_60_repeat_run_and_inputs_remain_unchanged(self):
        a=[inv()];b=[pay()];s=[prop(),GlobalGate()]
        before=(repr(a),repr(b),repr(s))
        first=run(invoices=a,payments=b,steps=s,tds_evidence=[tds()])
        second=run(invoices=a,payments=b,steps=s,tds_evidence=[tds()])
        self.assertEqual(first,second)
        self.assertEqual((repr(a),repr(b),repr(s)),before)
        self.assertFalse(first["original_source_workbooks_changed"])

    def test_61_locked_synthetic_v218_writer_preserves_J_invoice_M_sgst(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from sbi_r19_combined_synthetic_rehearsal import build_synthetic_fixture
        from sbi_r20_synthetic_review_writer import create_locked_synthetic_review_xlsx
        original,master=build_synthetic_fixture()
        written,receipt=create_locked_synthetic_review_xlsx(
            original,master,
            expected_source_sha256=sha256(original).hexdigest(),
            expected_master_sha256=sha256(master).hexdigest())
        source=load_workbook(BytesIO(original),read_only=True,data_only=False)
        output=load_workbook(BytesIO(written),read_only=True,data_only=False)
        try:
            self.assertEqual(source["Invoice Details."]["J1"].value,"Invoice No")
            self.assertEqual(source["Invoice Details."]["M1"].value,"SGST")
            self.assertEqual(output["Invoice Details."]["J2"].value,
                             source["Invoice Details."]["J2"].value)
            self.assertEqual(output["Invoice Details."]["M2"].value,
                             source["Invoice Details."]["M2"].value)
            self.assertEqual(output["PAYMNENT"]["I2"].value,
                             source["PAYMNENT"]["I2"].value)
            self.assertTrue(receipt["all_payment_statuses_locked_suspense"])
            self.assertFalse(receipt["real_v218_writer_verified"])
        finally:
            source.close()
            output.close()

    def test_62_accounting_does_not_claim_actual_v218_parity(self):
        x=run(tds_evidence=[tds()])
        self.assertEqual(x["stage"],STAGE)
        self.assertFalse(x["real_v218_financial_writer_amount_parity_verified"])
        self.assertFalse(x["real_53_column_report_financial_parity_verified"])
        self.assertFalse(x["full_master_v251_matrix_v239_certified"])
        self.assertEqual(x["real_financial_database_writes"],0)
        self.assertTrue(x["financial_apply_locked"])

if __name__=="__main__":
    unittest.main()
