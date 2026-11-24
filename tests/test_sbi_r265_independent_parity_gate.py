"""R26.5 exact-source SHA-parity and independent arithmetic TESTS, synthetic only."""
import sys
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import sbi_r265_independent_parity_gate as gate
from sbi_r26_independent_financial_oracle import Invoice, Payment, R26Refusal
from sbi_r262_rebuild_candidate_planner import fixture_digest, RebuildRefusal
from sbi_r263_global_allocation_shadow import (
    Proposal, SyntheticProof, GlobalGate, proposal_digest, R263Refusal,
)
from sbi_r264_financial_accounting_shadow import (
    SyntheticTDS, SyntheticCreditNote, accounting_digest,
    account_synthetic_only, R264Refusal,
)

MASTER=(("0001","SYNTHETIC ALPHA"),("0002","SYNTHETIC BETA"),("1","SYNTHETIC ALPHA"))

def inv(**kw):
    return replace(Invoice(
        "SYN-MXP-001","0001","SYNTHETIC ALPHA",
        "1000.00","90.00","90.00","1180.00","1180.00",
        date(2026,9,1),("2026-09",),
    ),**kw)

def pay(**kw):
    return replace(Payment(
        "SYN-PAY-001","0001","SYNTHETIC ALPHA","1160.00",
        date(2026,9,15),("2026-09",),("SYN-MXP-001",),
    ),**kw)

def prop(**kw):
    return replace(Proposal("SYN-PAY-001","SYN-MXP-001","1160.00"),**kw)

def tds(**kw):
    return replace(SyntheticTDS("SYN-TDS-001","SYN-PAY-001",
                                "SYN-MXP-001",2,"20.00"),**kw)

def cn(**kw):
    return replace(SyntheticCreditNote("SYN-CN-001","SYN-MXP-001",
                                       "20.00",date(2026,9,20)),**kw)

def proof(kind="PARTIAL", **kw):
    return replace(SyntheticProof(
        "SYN-PROOF-001",kind,"SYN-PAY-001","SYN-MXP-001"),**kw)

def test_args(invoices=None,payments=None,steps=None,
              proofs=(),tds_evidence=(),credit_notes=(),master=MASTER):
    invoices=[inv()] if invoices is None else list(invoices)
    payments=[pay()] if payments is None else list(payments)
    steps=[prop(),GlobalGate()] if steps is None else list(steps)
    proofs=list(proofs);tds_evidence=list(tds_evidence);credit_notes=list(credit_notes)
    master=list(master)
    return dict(
        invoices=invoices,payments=payments,master_rows=master,
        steps=steps,proofs=proofs,tds_evidence=tds_evidence,
        credit_notes=credit_notes,
        expected_fixture_sha256=fixture_digest(invoices,payments,master),
        expected_plan_sha256=proposal_digest(steps,proofs),
        expected_accounting_sha256=accounting_digest(tds_evidence,credit_notes),
    )

def qa(**kw):
    return gate.verify_synthetic_parity(**test_args(**kw))


class R265IndependentArithmeticQA(unittest.TestCase):
    def passcheck(self, **kw):
        r=qa(**kw)
        self.assertEqual(r["decision"],"PASS_SYNTHETIC_ARITHMETIC_ONLY")
        self.assertTrue(r["independent_arithmetic_pass"])
        self.assertFalse(r["full_v251_certified"])
        self.assertFalse(r["real_financial_rows_used"])
        self.assertTrue(r["financial_apply_locked"])

    def holdcheck(self, reason,**kw):
        r=qa(**kw)
        self.assertEqual(r["decision"],"R264_BLOCKED_NO_FINANCIAL_PARITY_CLAIM")
        self.assertIn(reason,r["r264_blockers"])
        self.assertFalse(r["independent_arithmetic_pass"])
        self.assertFalse(r["candidate_amounts_released"])

    def test_01_cash1160_no_inferred_tax(self):
        self.passcheck()
    def test_02_1160_cash_plus_documented_synthetic_20_tds(self):
        self.passcheck(tds_evidence=[tds()])
    def test_03_20_credit_note_without_tds(self):
        self.passcheck(credit_notes=[cn()])
    def test_04_bad_cash20_double_claimed_tds_and_cn(self):
        self.holdcheck("GROSS_CASH_TDS_CN_OVERSETTLEMENT",
                       tds_evidence=[tds()],credit_notes=[cn()])
    def test_05_tds_0(self):
        self.passcheck(payments=[pay(credit="1180.00")],
                       steps=[prop(credit_portion="1180.00"),GlobalGate()],
                       tds_evidence=[tds(rate_percent=0,withholding="0.00")])
    def test_06_tds_1(self):
        self.passcheck(payments=[pay(credit="1170.00")],
                       steps=[prop(credit_portion="1170.00"),GlobalGate()],
                       tds_evidence=[tds(rate_percent=1,withholding="10.00")])
    def test_07_tds_3(self):
        self.passcheck(payments=[pay(credit="1150.00")],
                       steps=[prop(credit_portion="1150.00"),GlobalGate()],
                       tds_evidence=[tds(rate_percent=3,withholding="30.00")])
    def test_08_half_up_rounding(self):
        i=inv(taxable="105.50",cgst="6.25",sgst="6.25",
              gross="118.00",outstanding="118.00")
        self.passcheck(invoices=[i],payments=[pay(credit="114.83")],
                       steps=[prop(credit_portion="114.83"),GlobalGate()],
                       tds_evidence=[tds(rate_percent=3,withholding="3.17")])
    def test_09_wrong_tds_amount_held(self):
        self.holdcheck("TDS_AMOUNT_OR_HALF_UP_RATE_MISMATCH",
                       tds_evidence=[tds(withholding="19.99")])
    def test_10_two_credit_notes_same_invoice_distinct_ids(self):
        self.passcheck(credit_notes=[cn(credit_gross="5.00"),
                                    cn(key="SYN-CN-002",credit_gross="5.00")])
    def test_11_duplicate_credit_note_id_refused(self):
        self.holdcheck("DUPLICATE_CREDIT_NOTE_KEY",credit_notes=[cn(),cn()])
    def test_12_credit_note_invalid_date(self):
        self.holdcheck("CREDIT_NOTE_BEFORE_INVOICE_ISSUE",
                       credit_notes=[cn(issue_date=date(2026,8,31))])
    def test_13_credit_note_over_amount(self):
        self.holdcheck("CREDIT_NOTE_EXCEEDS_INVOICE_GROSS",
                       credit_notes=[cn(credit_gross="1200.00")])
    def test_14_negative_credit_note_held(self):
        self.holdcheck("CREDIT_NOTE_NONPOSITIVE",
                       credit_notes=[cn(credit_gross="-2.00")])
    def test_15_independent_payment_split_partial(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="580.00")
        steps=[
            prop(kind="PARTIAL_REVIEW",credit_portion="600.00",proof_key="SYN-PROOF-001"),
            prop(kind="PARTIAL_REVIEW",payment_key="SYN-PAY-002",
                 credit_portion="580.00",proof_key="SYN-PROOF-002"),
            GlobalGate()]
        proofs=[proof(),proof(key="SYN-PROOF-002",payment_key="SYN-PAY-002")]
        self.passcheck(payments=[p1,p2],steps=steps,proofs=proofs)
    def test_16_partial_overinvoice_held(self):
        p1=pay(credit="600.00")
        p2=pay(key="SYN-PAY-002",credit="600.00")
        steps=[
            prop(kind="PARTIAL_REVIEW",credit_portion="600.00",proof_key="SYN-PROOF-001"),
            prop(kind="PARTIAL_REVIEW",payment_key="SYN-PAY-002",
                 credit_portion="600.00",proof_key="SYN-PROOF-002"),
            GlobalGate()]
        proofs=[proof(),proof(key="SYN-PROOF-002",payment_key="SYN-PAY-002")]
        self.holdcheck("SHADOW_INVOICE_OUTSTANDING_OVERALLOCATED",
                       payments=[p1,p2],steps=steps,proofs=proofs)
    def test_17_two_invoice_waterfall_cash_split(self):
        i1=inv(taxable="500.00",cgst="45.00",sgst="45.00",
               gross="590.00",outstanding="590.00")
        i2=replace(i1,key="SYN-MXP-002")
        p=pay(credit="1000.00",mxp_refs=())
        steps=[GlobalGate(),
               prop(kind="WATERFALL",credit_portion="590.00",
                    proof_key="SYN-PROOF-001"),
               prop(kind="WATERFALL",invoice_key="SYN-MXP-002",
                    credit_portion="410.00",proof_key="SYN-PROOF-002")]
        proofs=[proof("WATERFALL"),
                proof("WATERFALL",key="SYN-PROOF-002",invoice_key="SYN-MXP-002")]
        self.passcheck(invoices=[i1,i2],payments=[p],steps=steps,proofs=proofs)
    def test_18_waterfall_before_global_gate_holds(self):
        self.holdcheck("WATERFALL_BEFORE_GLOBAL_GATE",
                       payments=[pay(mxp_refs=())],
                       steps=[prop(kind="WATERFALL",proof_key="SYN-PROOF-001"),GlobalGate()],
                       proofs=[proof("WATERFALL")])
    def test_19_gst_later_180_cash_with_fictitious_proof(self):
        self.passcheck(payments=[pay(credit="180.00",gst_narration=True)],
                       steps=[prop(kind="GST_REVIEW",credit_portion="180.00",
                                   proof_key="SYN-PROOF-001"),GlobalGate()],
                       proofs=[proof("GST")])
    def test_20_gst_without_proof_holds(self):
        self.holdcheck("GST_COMPONENT_DOCUMENTARY_PROOF_REQUIRED",
                       payments=[pay(credit="180.00",gst_narration=True)],
                       steps=[prop(kind="GST_REVIEW",credit_portion="180.00"),GlobalGate()])
    def test_21_sbisa_with_fictitious_relationship_only(self):
        self.passcheck(invoices=[inv(sol="")],payments=[pay(sol="1")],
                       steps=[prop(kind="SBISA_REVIEW",proof_key="SYN-PROOF-001"),GlobalGate()],
                       proofs=[proof("SBISA")])
    def test_22_sbisa_without_synthetic_proof_holds(self):
        self.holdcheck("SBISA_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED",
                       invoices=[inv(sol="")],payments=[pay(sol="1")],
                       steps=[prop(kind="SBISA_REVIEW"),GlobalGate()])
    def test_23_cross_sol_with_fictitious_relationship_only(self):
        self.passcheck(payments=[pay(sol="0002",client="SYNTHETIC BETA")],
                       steps=[prop(kind="CROSS_SOL_REVIEW",
                                   proof_key="SYN-PROOF-001"),GlobalGate()],
                       proofs=[proof("CROSS_SOL")])
    def test_24_cross_sol_without_proof_holds(self):
        self.holdcheck("CROSS_SOL_DOCUMENTARY_RELATIONSHIP_NOT_VERIFIED",
                       payments=[pay(sol="0002",client="SYNTHETIC BETA")],
                       steps=[prop(kind="CROSS_SOL_REVIEW"),GlobalGate()])
    def test_25_dnm_never_enters_financial_cash(self):
        self.passcheck(payments=[pay(mxp_refs=())],
                       steps=[prop(kind="DNM_REVIEW"),GlobalGate()])
    def test_26_dnm_with_contradictory_ref_holds(self):
        self.holdcheck("CONTRADICTORY_MXP_REFERENCE",
                       payments=[pay(mxp_refs=("SYN-MXP-999",))],
                       steps=[prop(kind="DNM_REVIEW"),GlobalGate()])
    def test_27_invoice_s_numeric_zero_protected(self):
        self.holdcheck("ORIGINAL_K_OR_S_PROTECTED",
                       invoices=[inv(source_s_marker=0)])
    def test_28_payment_k_historical_marker_protected(self):
        self.holdcheck("ORIGINAL_K_OR_S_PROTECTED",
                       payments=[pay(original_k="OK")])
    def test_29_duplicate_invoice_id_refused(self):
        with self.assertRaisesRegex(R264Refusal,"SOURCE_DUPLICATE_IDENTITIES_REFUSED"):
            qa(invoices=[inv(),inv()])
    def test_30_duplicate_payment_id_refused(self):
        with self.assertRaisesRegex(R264Refusal,"SOURCE_DUPLICATE_IDENTITIES_REFUSED"):
            qa(payments=[pay(),pay()])
    def test_31_nonpositive_bank_credit_held(self):
        self.holdcheck("NONPOSITIVE_BANK_CREDIT_REFUSED",
                       payments=[pay(credit="-1.00")],steps=[GlobalGate()])
    def test_32_real_invoice_number_refused(self):
        with self.assertRaisesRegex(R26Refusal,"SYNTHETIC_INVOICE_REQUIRED"):
            qa(invoices=[inv(key="MXP19970")])
    def test_33_numeric_master_sol_refused(self):
        with self.assertRaisesRegex(RebuildRefusal,"SYNTHETIC_MASTER_ONLY"):
            qa(master=((1,"SYNTHETIC ALPHA"),))
    def test_34_finance_apply_unlock_refused(self):
        with self.assertRaisesRegex(gate.R265Refusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            gate.verify_synthetic_parity(**test_args(),financial_apply="ENABLED")
    def test_35_stale_source_hash_rejected_at_independent_layer(self):
        obj=test_args();obj["expected_fixture_sha256"]="0"*64
        with self.assertRaisesRegex(gate.R265Refusal,"INDEPENDENT_SOURCE_MASTER_MANIFEST_MISMATCH"):
            gate.verify_synthetic_parity(**obj)
    def test_36_stale_plan_hash_rejected_at_independent_layer(self):
        obj=test_args();obj["expected_plan_sha256"]="0"*64
        with self.assertRaisesRegex(gate.R265Refusal,"INDEPENDENT_PROPOSAL_MANIFEST_MISMATCH"):
            gate.verify_synthetic_parity(**obj)
    def test_37_stale_accounting_hash_rejected_at_independent_layer(self):
        obj=test_args();obj["expected_accounting_sha256"]="0"*64
        with self.assertRaisesRegex(gate.R265Refusal,"INDEPENDENT_ACCOUNTING_MANIFEST_MISMATCH"):
            gate.verify_synthetic_parity(**obj)
    def test_38_wrong_hash_format_rejected(self):
        obj=test_args();obj["expected_accounting_sha256"]="bogus"
        with self.assertRaisesRegex(gate.R265Refusal,"THREE_EXPLICIT_SHA256_MANIFESTS_REQUIRED"):
            gate.verify_synthetic_parity(**obj)
    def test_39_release_matrix_remains_false_even_with_synthetic_pass(self):
        x=gate.release_gate_matrix()
        self.assertTrue(x["oct27_master_owner_selected_dev_reference"])
        for key in (
            "oct27_master_row_exception_approval_complete",
            "excluded_149_rows_owner_review_complete",
            "complete_master_v251_matrix_v239_executable_certified",
            "real_bank_same_source_independent_parity_passed",
            "real_v218_writer_monetary_parity_passed",
            "real_53_column_report_amount_parity_passed",
            "real_staging_firebase_flask_authenticated",
            "real_aws_staging_postgres_backup_and_rollback",
            "finance_security_owner_signoff",
            "production_release_authorized",
        ):
            self.assertFalse(x[key])
        self.assertTrue(x["financial_apply_locked"])
    def test_40_independent_oracle_catches_forged_invoice_gap(self):
        obj=test_args()
        real=account_synthetic_only(**obj)
        bad=dict(real)
        bad["synthetic_invoice_illustrative_rows"]=(
            ("SYN-MXP-001","1180.00","1160.00","0.00","0.00","0.00"),
        )
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            r=gate.verify_synthetic_parity(**obj)
        self.assertEqual(r["decision"],"FAIL_INDEPENDENT_ARITHMETIC_MISMATCH")
        self.assertIn("INVOICE_BY_INVOICE_CASH_TDS_CREDIT_NOTE_PARITY",r["mismatch_codes"])
    def test_41_independent_oracle_catches_forged_payment_credit(self):
        obj=test_args(); bad=dict(account_synthetic_only(**obj))
        bad["synthetic_payment_unassigned_rows"]=(
            ("SYN-PAY-001","1160.00","1160.00","999.00"),
        )
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            r=gate.verify_synthetic_parity(**obj)
        self.assertIn("PAYMENT_BY_PAYMENT_BANK_CREDIT_PARITY",r["mismatch_codes"])
    def test_42_independent_oracle_catches_forged_total(self):
        obj=test_args();bad=dict(account_synthetic_only(**obj))
        bad["illustrative_tds_total"]="20.00"
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            r=gate.verify_synthetic_parity(**obj)
        self.assertIn("AGGREGATE_ILLUSTRATIVE_TDS_TOTAL_MISMATCH",r["mismatch_codes"])
    def test_43_independent_oracle_rejects_unlocked_candidate_claim(self):
        obj=test_args();bad=dict(account_synthetic_only(**obj))
        bad["financial_apply_locked"]=False
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            with self.assertRaisesRegex(gate.R265Refusal,"UNAUTHORIZED_FINANCIAL_RELEASE_CLAIM"):
                gate.verify_synthetic_parity(**obj)
    def test_44_independent_oracle_rejects_forged_full_certification(self):
        obj=test_args();bad=dict(account_synthetic_only(**obj))
        bad["full_master_v251_matrix_v239_certified"]=True
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            with self.assertRaisesRegex(gate.R265Refusal,"UNAUTHORIZED_FINANCIAL_RELEASE_CLAIM"):
                gate.verify_synthetic_parity(**obj)
    def test_45_independent_oracle_rejects_forged_writer_parity(self):
        obj=test_args();bad=dict(account_synthetic_only(**obj))
        bad["real_v218_financial_writer_amount_parity_verified"]=True
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            with self.assertRaisesRegex(gate.R265Refusal,"UNAUTHORIZED_FINANCIAL_RELEASE_CLAIM"):
                gate.verify_synthetic_parity(**obj)
    def test_46_independent_oracle_rejects_forged_production_rows(self):
        obj=test_args();bad=dict(account_synthetic_only(**obj))
        bad["real_financial_database_writes"]=1
        with patch.object(gate,"account_synthetic_only",return_value=bad):
            with self.assertRaisesRegex(gate.R265Refusal,"UNAUTHORIZED_FINANCIAL_RELEASE_CLAIM"):
                gate.verify_synthetic_parity(**obj)
    def test_47_repeated_execution_deterministic_and_no_mutation(self):
        obj=test_args(tds_evidence=[tds()])
        before=repr(obj)
        a=gate.verify_synthetic_parity(**obj)
        b=gate.verify_synthetic_parity(**obj)
        self.assertEqual(a,b)
        self.assertEqual(repr(obj),before)
    def test_48_witness_cash_and_net_do_not_certify_money(self):
        r=gate.independent_cash_tax_credit_reference(
            [inv()],[pay()],[prop(),GlobalGate()],[],[])
        self.assertEqual(r["cash"],"1160.00")
        self.assertEqual(r["tds"],"0.00")
        self.assertTrue(r["invoice_equation_conserved"])
        self.assertTrue(r["credit_conserved"])
    def test_49_unchanged_writer_preserves_original_columns_synthetic(self):
        from sbi_r19_combined_synthetic_rehearsal import build_synthetic_fixture
        from sbi_r20_synthetic_review_writer import create_locked_synthetic_review_xlsx
        from sbi_r18_output_parity_gate import verify_xlsx_output_structure
        from io import BytesIO
        from hashlib import sha256
        from openpyxl import load_workbook
        raw,master=build_synthetic_fixture()
        out,receipt=create_locked_synthetic_review_xlsx(
            raw,master,expected_source_sha256=sha256(raw).hexdigest(),
            expected_master_sha256=sha256(master).hexdigest())
        r=verify_xlsx_output_structure(
            raw,out,expected_source_sha256=sha256(raw).hexdigest(),
            expected_candidate_sha256=sha256(out).hexdigest())
        self.assertTrue(receipt["all_payment_statuses_locked_suspense"])
        self.assertFalse(receipt["real_v218_writer_verified"])
        original=load_workbook(BytesIO(raw),read_only=True)
        output=load_workbook(BytesIO(out),read_only=True)
        try:
            for c in ("G1","H1","J1","K1","L1","M1","N1","S2"):
                self.assertEqual(original["Invoice Details."][c].value,
                                 output["Invoice Details."][c].value)
            self.assertEqual(original["PAYMNENT"]["I2"].value,
                             output["PAYMNENT"]["I2"].value)
        finally:
            original.close();output.close()
    def test_50_all_remains_synthetic_no_prod_permission(self):
        r=qa(tds_evidence=[tds()])
        self.assertFalse(r["real_v218_writer_monetary_parity_verified"])
        self.assertFalse(r["finance_release_authorized"])
        self.assertTrue(r["financial_apply_locked"])
        self.assertEqual(r["number_of_synthetic_invoices"],1)
        self.assertEqual(r["number_of_synthetic_payments"],1)


if __name__=="__main__":
    unittest.main()
