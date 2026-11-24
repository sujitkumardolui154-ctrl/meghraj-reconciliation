"""Synthetic-only Case 2.6 method and release-gate adversarial regression."""
import sys,unittest
from dataclasses import replace
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r269_case22_independent_fresh_workbook import (
    FreshWorkbook,ScopedInvoice,ScopedBank,fresh_workbook_digest)
from sbi_r269_case26_method_coverage_rehearsal import (
    InvoiceDetail,BankDetail,MethodStep,Case26Refusal,evidence_digest,rehearse_methods,
    DNM,WATERFALL)
from sbi_r269_case26_external_release_gate import (
    ExternalEvidenceDeclaration,FinanceReleaseRefusal,review_release_readiness,GATES)

UP="SYN-CASE26-UPLOAD"
SHA="a"*64
MASTER_SHA="b"*64
D=date(2026,9,1)

def inv(**kw):
    return replace(InvoiceDetail(2,"MXP10001","0001","SYNTHETIC ALPHA",
        D,("2026-09",),"1000.00","90.00","90.00","1180.00"),**kw)

def bank(**kw):
    return replace(BankDetail(2,"SYN-PAY-002","0001","SYNTHETIC ALPHA",
        date(2026,9,15),("2026-09",),"1160.00",
        "POSTAGE SEPTEMBER 2026 MXP10001"),**kw)

def step(**kw):
    return replace(MethodStep("SYN-PAY-002","MXP10001","1160.00",
        "EXACT_MXP_REVIEW","SYN-EXACT-001",2),**kw)

def package(ivs=None,pays=None,steps=None,master=None,relationships=(),upload=UP):
    ivs=tuple((inv(),) if ivs is None else ivs)
    pays=tuple((bank(),) if pays is None else pays)
    steps=tuple((step(),) if steps is None else steps)
    master=tuple((("0001","SYNTHETIC ALPHA"),) if master is None else master)
    relationships=tuple(relationships)
    wb=FreshWorkbook(upload,SHA,MASTER_SHA,
        tuple(ScopedInvoice(upload,x.invoice_no,x.source_row,x.gross) for x in ivs),
        tuple(ScopedBank(upload,x.bank_key,x.source_row,x.credit) for x in pays))
    return dict(workbook=wb,invoices=ivs,banks=pays,steps=steps,
        master_pairs=master,relationships=relationships,
        expected_workbook_digest=fresh_workbook_digest(wb),
        expected_evidence_digest=evidence_digest(ivs,pays,steps,master,relationships))

def run(**kw):
    return rehearse_methods(**package(**kw))

def altered(kw=None,**overrides):
    d=package(**(kw or {}))
    d.update(overrides)
    return d

def waterfall(reverse=False,extra_method=False):
    a=inv(gross="600.00",taxable="600.00",cgst="0.00",sgst="0.00")
    b=inv(source_row=3,invoice_no="MXP10002",gross="500.00",
          taxable="500.00",cgst="0.00",sgst="0.00",
          issue_date=D+timedelta(days=1))
    p=bank(credit="1000.00",narration="POSTAGE SEPTEMBER 2026")
    s1=step(portion="600.00",method=WATERFALL,tds_rate=None,
            proof_tag="SYN-WATERFALL-1")
    s2=step(invoice_no="MXP10002",portion="400.00",method=WATERFALL,
            tds_rate=None,proof_tag="SYN-WATERFALL-2")
    return dict(ivs=(a,b),pays=(p,),steps=(s2,s1) if reverse else (s1,s2))


class Case26MethodQA(unittest.TestCase):
    def fails(self,code, **kw):
        with self.assertRaisesRegex(Case26Refusal,code):
            run(**kw)

    def test_01_full_2pct_exact_cash(self):
        x=run()
        self.assertEqual(x["cash_reserved"],"1160.00")
        self.assertEqual(x["invoice_cash_coverage_gap_not_receivable"],"20.00")
        self.assertEqual(x["cash_unassigned"],"0.00")
        self.assertFalse(x["production_release_authorized"])
        self.assertEqual(x["real_bank_allocations"],0)

    def test_02_zero_percent(self):
        x=run(pays=(bank(credit="1180.00"),),
              steps=(step(portion="1180.00",tds_rate=0),))
        self.assertEqual(x["cash_reserved"],"1180.00")

    def test_03_one_percent(self):
        x=run(pays=(bank(credit="1170.00"),),
              steps=(step(portion="1170.00",tds_rate=1),))
        self.assertEqual(x["cash_reserved"],"1170.00")

    def test_04_three_percent(self):
        x=run(pays=(bank(credit="1150.00"),),
              steps=(step(portion="1150.00",tds_rate=3),))
        self.assertEqual(x["cash_reserved"],"1150.00")

    def test_05_half_up_rounding(self):
        # 1% of 1001.50 = 10.015 -> 10.02 (ROUND_HALF_UP)
        ivs=(inv(taxable="1001.50",gross="1181.50"),)
        pays=(bank(credit="1171.48"),)
        x=run(ivs=ivs,pays=pays,steps=(step(portion="1171.48",tds_rate=1),))
        self.assertEqual(x["cash_reserved"],"1171.48")

    def test_06_bad_tds_rate(self):
        self.fails("EXACT_MATCH_TDS_RATE",steps=(step(tds_rate=4),))

    def test_07_wrong_tds_amount(self):
        self.fails("NET_TDS_CREDIT_MATH",pays=(bank(credit="1159.00"),),
                   steps=(step(portion="1159.00"),))

    def test_08_reference_required(self):
        self.fails("EXPLICIT_MXP_NARRATION",pays=(bank(narration="POSTAGE SEPTEMBER"),))

    def test_09_contradictory_reference(self):
        self.fails("EXPLICIT_MXP_NARRATION",pays=(
            bank(narration="POSTAGE MXP10001 MXP10002"),))

    def test_10_wrong_client_identity(self):
        self.fails("EXACT_METHOD_SOL_CLIENT",pays=(bank(client="SYNTHETIC BETA"),))

    def test_11_older_than_180_days(self):
        self.fails("BANK_INVOICE_180_DAY",pays=(bank(bank_date=D+timedelta(days=181)),))

    def test_12_bank_before_invoice(self):
        self.fails("BANK_INVOICE_180_DAY",pays=(bank(bank_date=D-timedelta(days=1)),))

    def test_13_service_period_different(self):
        self.fails("SERVICE_PERIOD_MULTI_MONTH",pays=(bank(periods=("2026-08",)),))

    def test_14_complete_multi_month_period(self):
        ivs=(inv(periods=("2026-03","2026-04","2026-05"),issue_date=date(2026,7,1)),)
        pays=(bank(periods=("2026-03","2026-04","2026-05"),
                   bank_date=date(2026,9,15)),)
        self.assertEqual(run(ivs=ivs,pays=pays)["cash_reserved"],"1160.00")

    def test_15_incomplete_multi_month(self):
        ivs=(inv(periods=("2026-03","2026-04","2026-05"),issue_date=date(2026,7,1)),)
        self.fails("SERVICE_PERIOD_MULTI_MONTH",ivs=ivs,pays=(
            bank(periods=("2026-03","2026-05")),))

    def test_16_taxable_plus_gst_mismatch(self):
        self.fails("INVOICE_GST_COMPONENT_TOTAL",ivs=(inv(cgst="89.99"),))

    def test_17_exact_source_gross_mismatch(self):
        data=package()
        d=replace(data["invoices"][0],gross="1181.00")
        data["invoices"]=(d,)
        data["expected_evidence_digest"]=evidence_digest(
            data["invoices"],data["banks"],data["steps"],
            data["master_pairs"],data["relationships"])
        with self.assertRaisesRegex(Case26Refusal,"INVOICE_SOURCE_OR_PROTECTION"):
            rehearse_methods(**data)

    def test_18_payment_source_credit_mismatch(self):
        data=package()
        p=replace(data["banks"][0],credit="1161.00")
        data["banks"]=(p,)
        data["expected_evidence_digest"]=evidence_digest(
            data["invoices"],data["banks"],data["steps"],
            data["master_pairs"],data["relationships"])
        with self.assertRaisesRegex(Case26Refusal,"BANK_SOURCE_OR_PROTECTION"):
            rehearse_methods(**data)

    def test_19_negative_bank_credit(self):
        self.fails("INVALID_OR_SUBPAISE_AMOUNT",pays=(bank(credit="-1.00"),))

    def test_20_partial_payment(self):
        x=run(pays=(bank(credit="500.00"),),
              steps=(step(portion="500.00",method="PARTIAL_REVIEW",
                          tds_rate=None,proof_tag="SYN-PARTIAL-1"),))
        self.assertEqual(x["cash_unassigned"],"0.00")
        self.assertFalse(x["real_tds_gst_cn_documents_verified"])

    def test_21_partial_gross_not_allowed(self):
        self.fails("PARTIAL_MUST_BE_LESS",pays=(bank(credit="1180.00"),),
              steps=(step(portion="1180.00",method="PARTIAL_REVIEW",
                          tds_rate=None,proof_tag="SYN-PARTIAL-1"),))

    def test_22_documented_gst_component_review(self):
        x=run(pays=(bank(credit="180.00",
              narration="GST POSTAGE SEPTEMBER 2026 MXP10001"),),
              steps=(step(portion="180.00",method="GST_COMPONENT_REVIEW",
                         tds_rate=None,proof_tag="SYN-GST-001"),))
        self.assertEqual(x["cash_reserved"],"180.00")

    def test_23_wrong_gst_amount(self):
        self.fails("GST_LATER_COMPONENT",pays=(bank(credit="179.99",
              narration="GST MXP10001"),),
              steps=(step(portion="179.99",method="GST_COMPONENT_REVIEW",
                          tds_rate=None,proof_tag="SYN-GST-001"),))

    def test_24_gst_without_narration(self):
        self.fails("GST_LATER_COMPONENT",pays=(bank(credit="180.00"),),
              steps=(step(portion="180.00",method="GST_COMPONENT_REVIEW",
                         tds_rate=None,proof_tag="SYN-GST-001"),))

    def test_25_sbisa_blank_sol_one(self):
        x=run(ivs=(inv(sol="",client="SYNTHETIC SBISA"),),
              pays=(bank(sol="1",client="SYNTHETIC SBISA",credit="500.00",
                         narration="SBISA POSTAGE SEPTEMBER"),),
              steps=(step(portion="500.00",method="SBISA_REVIEW",tds_rate=None,
                          proof_tag="SYN-SBISA-1"),))
        self.assertIn("SBISA_REVIEW",x["methods_rehearsed"])

    def test_26_sbisa_wrong_sol(self):
        self.fails("SBISA_EXCEPTION",ivs=(inv(sol="",client="SYNTHETIC SBISA"),),
              pays=(bank(sol="0001",client="SYNTHETIC SBISA",credit="500.00",
                         narration="SBISA POSTAGE SEPTEMBER"),),
              steps=(step(portion="500.00",method="SBISA_REVIEW",tds_rate=None,
                          proof_tag="SYN-SBISA-1"),))

    def cross(self,relationships=(("0002","0003"),),master=None):
        return dict(ivs=(inv(sol="0003",client="SYNTHETIC GAMMA"),),
                    pays=(bank(sol="0002",client="SYNTHETIC BETA"),),
                    steps=(step(method="CROSS_SOL_REVIEW",tds_rate=None,
                                proof_tag="SYN-CROSS-1"),),
                    master=master if master is not None else (
                        ("0002","SYNTHETIC BETA"),
                        ("0003","SYNTHETIC GAMMA")),
                    relationships=relationships)

    def test_27_two_sided_cross_sol(self):
        self.assertIn("CROSS_SOL_REVIEW",run(**self.cross())["methods_rehearsed"])

    def test_28_cross_sol_no_relationship(self):
        self.fails("CROSS_SOL_OFFICIAL_TWO_SIDED",**self.cross(relationships=()))

    def test_29_cross_sol_no_master_pair(self):
        self.fails("CROSS_SOL_OFFICIAL_TWO_SIDED",
                   **self.cross(master=(("0002","SYNTHETIC BETA"),)))

    def test_30_unique_same_sol_without_reference(self):
        x=run(pays=(bank(narration="POSTAGE SEPTEMBER 2026"),),
              steps=(step(method="SAME_SOL_REVIEW",tds_rate=None,
                          proof_tag="SYN-SAME-1"),))
        self.assertIn("SAME_SOL_REVIEW",x["methods_rehearsed"])

    def test_31_ambiguous_same_sol_without_reference(self):
        ivs=(inv(),inv(source_row=3,invoice_no="MXP10002"))
        self.fails("AMBIGUOUS_SAME_SOL",ivs=ivs,
            pays=(bank(narration="POSTAGE SEPTEMBER 2026"),),
            steps=(step(method="SAME_SOL_REVIEW",tds_rate=None,
                        proof_tag="SYN-SAME-1"),))

    def test_32_multi_invoice_waterfall(self):
        x=run(**waterfall())
        self.assertEqual(x["cash_reserved"],"1000.00")
        self.assertEqual(len(x["shadow_edges"]),2)
        self.assertIn(WATERFALL,x["methods_rehearsed"])
        self.assertEqual(x["invoice_cash_coverage_gap_not_receivable"],"100.00")

    def test_33_waterfall_oldest_invoice_first(self):
        self.fails("WATERFALL_OLDEST_INVOICE",**waterfall(reverse=True))

    def test_34_waterfall_requires_multi_invoice(self):
        self.fails("MULTI_INVOICE_WATERFALL",pays=(bank(
            narration="POSTAGE SEPTEMBER 2026"),),
            steps=(step(method=WATERFALL,tds_rate=None,
                        proof_tag="SYN-WATERFALL-1"),))

    def test_35_provisional_dnm_never_reserved(self):
        x=run(pays=(bank(narration="POSTAGE SEPTEMBER 2026"),),
              steps=(step(portion="0.00",method=DNM,tds_rate=None,
                          proof_tag="SYN-DNM-1"),))
        self.assertEqual(x["cash_reserved"],"0.00")
        self.assertEqual(len(x["dnm_provisional_unreserved"]),1)

    def test_36_dnm_nonzero_cash_refused(self):
        self.fails("PROVISIONAL_DNM_MUST_NEVER_RESERVE",
                   pays=(bank(narration="POSTAGE SEPTEMBER 2026"),),
                   steps=(step(method=DNM,tds_rate=None,proof_tag="SYN-DNM-1"),))

    def test_37_dnm_and_reserved_same_bank_refused(self):
        self.fails("DNM_PROVISIONAL_AND_RESERVED_SAME_BANK",
             pays=(bank(narration="POSTAGE SEPTEMBER 2026"),),
             steps=(step(portion="0.00",method=DNM,tds_rate=None,
                         proof_tag="SYN-DNM-1"),
                    step(method="SAME_SOL_REVIEW",tds_rate=None,
                         proof_tag="SYN-SAME-1")))

    def test_38_wrong_workbook_digest(self):
        d=package()
        d["expected_workbook_digest"]="f"*64
        with self.assertRaisesRegex(Case26Refusal,"SCOPED_WORKBOOK_SOURCE_SHA"):
            rehearse_methods(**d)

    def test_39_wrong_method_evidence_sha(self):
        d=package()
        d["expected_evidence_digest"]="f"*64
        with self.assertRaisesRegex(Case26Refusal,"SOURCE_METHOD_EVIDENCE_SHA"):
            rehearse_methods(**d)

    def test_40_duplicate_bank_invoice_edge(self):
        self.fails("DUPLICATE_METHOD_ALLOCATION_EDGE",steps=(step(),step()))

    def test_41_subpaise_money(self):
        self.fails("INVALID_OR_SUBPAISE_AMOUNT",steps=(step(portion="1160.001"),))

    def test_42_unknown_method(self):
        self.fails("UNSUPPORTED_OR_UNSCOPED_METHOD",steps=(step(method="LIVE_APPLY"),))

    def test_43_unknown_bank(self):
        self.fails("UNKNOWN_BANK_OR_INVOICE",steps=(step(bank_key="SYN-PAY-999"),))

    def test_44_invalid_proof_tag(self):
        self.fails("SYNTHETIC_DOCUMENTARY_PROOF",steps=(step(proof_tag="APPROVED"),))

    def test_45_protected_bank_original_k(self):
        d=package();w=d["workbook"]
        d["workbook"]=replace(w,banks=(replace(w.banks[0],original_k="OK"),))
        d["expected_workbook_digest"]=fresh_workbook_digest(d["workbook"])
        with self.assertRaisesRegex(Case26Refusal,"BANK_SOURCE_OR_PROTECTION"):
            rehearse_methods(**d)

    def test_46_protected_invoice_original_s(self):
        d=package();w=d["workbook"]
        d["workbook"]=replace(w,invoices=(replace(w.invoices[0],original_s="PAID"),))
        d["expected_workbook_digest"]=fresh_workbook_digest(d["workbook"])
        with self.assertRaisesRegex(Case26Refusal,"INVOICE_SOURCE_OR_PROTECTION"):
            rehearse_methods(**d)

    def test_47_financial_apply_locked(self):
        d=package();d["financial_apply"]="ENABLED"
        with self.assertRaisesRegex(Case26Refusal,"FINANCIAL_APPLY_LOCK"):
            rehearse_methods(**d)

    def test_48_deterministic_replay_no_history(self):
        d=package()
        a=rehearse_methods(**d);b=rehearse_methods(**d)
        self.assertEqual(a,b)
        self.assertTrue(a["one_upload_option_b"])

    def test_49_two_uploads_distinct_scopes(self):
        a=run()
        b=run(upload="SYN-CASE26-SECOND")
        self.assertNotEqual(a["workbook_digest"],b["workbook_digest"])
        self.assertEqual(a["cash_reserved"],b["cash_reserved"])

    def test_50_no_real_writer_and_no_certification(self):
        a=run()
        self.assertIsNone(a["final_payment_status"])
        self.assertFalse(a["full_matching_method_coverage_certified"])
        self.assertFalse(a["real_tds_gst_cn_documents_verified"])
        self.assertFalse(a["official_bank_utr_verified"])
        self.assertTrue(a["financial_apply_locked"])
        self.assertEqual(a["real_database_writes"],0)


class Case26ReleaseGateQA(unittest.TestCase):
    def test_51_external_evidence_all_blocked(self):
        r=review_release_readiness(run())
        self.assertEqual(len(r["gates"]),len(GATES))
        self.assertEqual(r["verified_external_evidence_gate_count"],0)
        self.assertFalse(r["production_release_authorized"])

    def test_52_external_declaration_does_not_certify(self):
        e=ExternalEvidenceDeclaration(GATES[0],"SYN-RECEIPT-0001","a"*64)
        r=review_release_readiness(run(),(e,))
        self.assertEqual(r["verified_external_evidence_gate_count"],0)
        self.assertEqual(r["external_evidence_caller_declarations_only"],1)
        self.assertFalse(r["full_v251_v239_financial_certification"])

    def test_53_all_declarations_still_block(self):
        claims=tuple(ExternalEvidenceDeclaration(g,f"SYN-EVID-{n:04d}","a"*64)
                     for n,g in enumerate(GATES))
        r=review_release_readiness(run(),claims)
        self.assertEqual(r["verified_external_evidence_gate_count"],0)
        self.assertFalse(r["production_release_authorized"])

    def test_54_fake_signed_claim_denied(self):
        e=ExternalEvidenceDeclaration(GATES[0],"SYN-RECEIPT-0001","a"*64,
                                      "INDEPENDENT_APPROVED")
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNVERIFIED_OR_FORGED"):
            review_release_readiness(run(),(e,))

    def test_55_duplicate_gate_denied(self):
        e=ExternalEvidenceDeclaration(GATES[0],"SYN-RECEIPT-0001","a"*64)
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNVERIFIED_OR_FORGED"):
            review_release_readiness(run(),(e,e))

    def test_56_unknown_gate_denied(self):
        e=ExternalEvidenceDeclaration("PRODUCTION_UNLOCK","SYN-RECEIPT-0001","a"*64)
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNVERIFIED_OR_FORGED"):
            review_release_readiness(run(),(e,))

    def test_57_invalid_digest_denied(self):
        e=ExternalEvidenceDeclaration(GATES[0],"SYN-RECEIPT-0001","A"*64)
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNVERIFIED_OR_FORGED"):
            review_release_readiness(run(),(e,))

    def test_58_nonlocked_release_denied(self):
        with self.assertRaisesRegex(FinanceReleaseRefusal,"LOCK"):
            review_release_readiness(run(),financial_apply="ENABLED")

    def test_59_forged_method_finance_status_denied(self):
        x={**run(),"final_payment_status":"OK"}
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNSAFE_OR_FORGED"):
            review_release_readiness(x)

    def test_60_forged_method_write_denied(self):
        x={**run(),"real_database_writes":1}
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNSAFE_OR_FORGED"):
            review_release_readiness(x)

    def test_61_forged_engine_certification_denied(self):
        x={**run(),"full_v251_v239_certified":True}
        with self.assertRaisesRegex(FinanceReleaseRefusal,"UNSAFE_OR_FORGED"):
            review_release_readiness(x)

    def test_62_release_gate_no_external_mutations(self):
        original=run()
        result=review_release_readiness(original)
        self.assertFalse(result["real_v218_writer_authorized"])
        self.assertFalse(result["real_payment_status_assignment_authorized"])
        self.assertFalse(result["real_original_source_or_bank_verified"])
        self.assertEqual(original["real_bank_allocations"],0)

if __name__=="__main__":
    unittest.main()
