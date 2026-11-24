"""R26.7 v2.18 artifact_tool writer pure-contract tests; SYN fixtures only."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r267_readonly_real_candidate_engine import (
    InvoiceInput,BankInput,plan_review_only,
)
from sbi_r267_artifact_v218_review_writer import (
    PAYMENT_HEADERS,INVOICE_HEADERS,
    build_preview_cells,apply_locked_model_columns,
    R267WriterRefusal,
)

H="a"*64
MASTER=(("0001","SYNTHETIC ALPHA"),)
def inv(**kw):
    return replace(InvoiceInput(2,"MXP10001","0001","SYNTHETIC ALPHA",
        date(2026,9,1),("2026-09",),"1000","90","90","1180"),**kw)
def pay(**kw):
    return replace(BankInput(2,"0001","SYNTHETIC ALPHA",
        date(2026,9,15),("2026-09",),"MXP10001 SEPTEMBER 2026","1160"),**kw)
def snapshot(invoices=None,payments=None,holds=(),
             pcount=1,icount=1):
    return SimpleNamespace(
        invoices=tuple([inv()] if invoices is None else invoices),
        payments=tuple([pay()] if payments is None else payments),
        master_pairs=MASTER,source_sha256=H,master_sha256=H,
        review_only_hold_codes=tuple(holds),
        source_preflight={"invoice_data_rows":icount,"payment_data_rows":pcount},
    )
def plan(s):
    return plan_review_only(list(s.invoices),list(s.payments),
        list(s.master_pairs),source_sha256=H,master_sha256=H)
def cells(s=None,r=None):
    s=s or snapshot()
    return build_preview_cells(s,r or plan(s))

class CaptureRange:
    def __init__(self,container,key):
        self.container=container
        self.key=key
    @property
    def values(self):
        return self.container.get(self.key)
    @values.setter
    def values(self,v):
        self.container[self.key]=v

class CaptureSheet:
    def __init__(self):
        self.cells={}
    def get_range(self,name):
        return CaptureRange(self.cells,name)

class CaptureSheets:
    def __init__(self):
        self.items={"PAYMNENT":CaptureSheet(),"Invoice Details.":CaptureSheet()}
    def get_item(self,name):
        return self.items[name]

class CaptureBook:
    def __init__(self):
        self.worksheets=CaptureSheets()

class R267LockedV218WriterTests(unittest.TestCase):
    def test_01_exact_payment_header_lock(self):
        self.assertEqual(PAYMENT_HEADERS,(
            "Model Reconciliation Status","Model Reconciliation Remarks",
            "Model Invoice No (Candidate if SUSPENSE)","Model Invoice Source Row",
            "Model Match Method","Model TDS Rate % (Inferred)",
            "Model Expected Credit (Hypothesis)","Model Signed Residual",
            "Model Service / Evidence","Model SOL ID","Model Proper Client Name"))
    def test_02_exact_invoice_header_lock(self):
        self.assertEqual(INVOICE_HEADERS,(
            "Model SOL ID","Model Proper Client Name",
            "Model Linked Bank Row (Working)","Model Linked Bank Credit",
            "Model Match Evidence"))
    def test_03_every_bank_status_stays_suspense(self):
        p,i=cells()
        self.assertEqual(p[0][0],"SUSPENSE")
        self.assertNotIn("OK",repr(p[0]))
    def test_04_candidate_mxp_in_O_and_invoice_source_in_P(self):
        p,i=cells()
        self.assertEqual(p[0][2],"MXP10001")
        self.assertEqual(p[0][3],2)
    def test_05_candidate_tds_in_R(self):
        p,i=cells()
        self.assertEqual(p[0][5],2)
        self.assertEqual(p[0][6],1160.0)
    def test_06_original_model_SOL_as_text(self):
        p,i=cells()
        self.assertEqual(p[0][9],"0001")
        self.assertEqual(i[0][0],"0001")
    def test_07_verified_official_client_name_in_W_and_AJ(self):
        p,i=cells()
        self.assertEqual(p[0][10],"SYNTHETIC ALPHA")
        self.assertEqual(i[0][1],"SYNTHETIC ALPHA")
    def test_08_invoice_working_link_but_no_paid_status(self):
        p,i=cells()
        self.assertEqual(i[0][2],2)
        self.assertEqual(i[0][3],1160.0)
        self.assertIn("CANDIDATE CASH ONLY",i[0][4])
    def test_09_unknown_client_not_silently_substituted(self):
        s=snapshot(payments=[pay(client="SYNTHETIC UNKNOWN")])
        p,i=cells(s)
        self.assertIsNone(p[0][10])
        self.assertIsNone(p[0][2])
    def test_10_paid_invoice_s_protected_model(self):
        s=snapshot(invoices=[inv(original_s=0)])
        p,i=cells(s)
        self.assertEqual(p[0][0],"SUSPENSE")
        self.assertIn("PROTECTED_INVOICE_S_NONBLANK",i[0][4])
        self.assertIsNone(i[0][2])
    def test_11_paid_bank_K_protected(self):
        s=snapshot(payments=[pay(original_k="OK")])
        p,i=cells(s)
        self.assertIn("PROTECTED_BANK_K_NONBLANK",p[0][1])
    def test_12_no_bank_credit_without_exact_ref(self):
        s=snapshot(payments=[pay(description="MXP99999 SEPTEMBER 2026")])
        p,i=cells(s)
        self.assertIsNone(p[0][2])
        self.assertIn("NAMED_MXP_UNAVAILABLE",p[0][1])
    def test_13_nonnumeric_bank_source_extra_row_suspense(self):
        s=snapshot(holds=[("PAYMENT",3,"BANK_CREDIT_BLANK_OR_NONNUMERIC")],pcount=2)
        p,i=cells(s)
        self.assertEqual(len(p),2)
        self.assertEqual(p[1][0],"SUSPENSE")
        self.assertIn("BANK_CREDIT",p[1][1])
        self.assertIsNone(p[1][6])
    def test_14_invoice_missing_money_row_quarantined(self):
        s=snapshot(holds=[("INVOICE",3,"INVOICE_CORE_MONEY_NONNUMERIC")],icount=2)
        p,i=cells(s)
        self.assertEqual(len(i),2)
        self.assertIsNone(i[1][3])
        self.assertIn("NONNUMERIC",i[1][4])
    def test_15_missing_source_row_map_refused(self):
        s=snapshot(pcount=2)
        with self.assertRaisesRegex(R267WriterRefusal,"PAYMENT_ROW_MAPPING_INCOMPLETE"):
            cells(s)
    def test_16_missing_invoice_row_map_refused(self):
        s=snapshot(icount=2)
        with self.assertRaisesRegex(R267WriterRefusal,"INVOICE_ROW_MAPPING_INCOMPLETE"):
            cells(s)
    def test_17_source_sha_mismatch_refused(self):
        s=snapshot();r=dict(plan(s));r["source_sha256"]="0"*64
        with self.assertRaisesRegex(R267WriterRefusal,"SOURCE_OR_MASTER_SHA_MISMATCH"):
            cells(s,r)
    def test_18_master_sha_mismatch_refused(self):
        s=snapshot();r=dict(plan(s));r["master_sha256"]="0"*64
        with self.assertRaisesRegex(R267WriterRefusal,"SOURCE_OR_MASTER_SHA_MISMATCH"):
            cells(s,r)
    def test_19_planner_release_forgery_refused(self):
        s=snapshot();r=dict(plan(s));r["complete_master_v251_matrix_v239_certified"]=True
        with self.assertRaisesRegex(R267WriterRefusal,"UNAUTHORIZED_LEDGER_APPLY_OR_RELEASE"):
            cells(s,r)
    def test_20_planner_fake_OK_refused(self):
        s=snapshot();r=dict(plan(s));r["all_real_bank_statuses"]="OK"
        with self.assertRaisesRegex(R267WriterRefusal,"UNAUTHORIZED_LEDGER_APPLY_OR_RELEASE"):
            cells(s,r)
    def test_21_duplicate_model_candidate_same_payment_refused(self):
        s=snapshot();r=dict(plan(s))
        r["candidate_rows"]=r["candidate_rows"]+r["candidate_rows"]
        with self.assertRaisesRegex(R267WriterRefusal,"AMBIGUOUS_MULTI_INVOICE_PAYMENT"):
            cells(s,r)
    def test_22_unverified_invoice_no_refused(self):
        s=snapshot();r=dict(plan(s))
        r["candidate_rows"]=((2,"MXP99999","1160.00","EXACT_MXP_TDS_REVIEW",2),)
        with self.assertRaisesRegex(R267WriterRefusal,"CANDIDATE_NOT_IN_VERIFIED_SNAPSHOT"):
            cells(s,r)
    def test_23_wrong_plan_invoices_count_refused(self):
        s=snapshot();r=dict(plan(s));r["source_invoice_count"]=3
        with self.assertRaisesRegex(R267WriterRefusal,"REVIEW_INVOICE_COUNT_MISMATCH"):
            cells(s,r)
    def test_24_both_header_rows_written_only_model_columns(self):
        s=snapshot();b=CaptureBook()
        receipt=apply_locked_model_columns(b,s,plan(s))
        self.assertEqual(b.worksheets.items["PAYMNENT"].cells["M1:W1"],[list(PAYMENT_HEADERS)])
        self.assertEqual(b.worksheets.items["Invoice Details."].cells["AI1:AM1"],[list(INVOICE_HEADERS)])
        self.assertEqual(set(b.worksheets.items["PAYMNENT"].cells),{"M1:W1","M2:W2"})
        self.assertEqual(set(b.worksheets.items["Invoice Details."].cells),{"AI1:AM1","AI2:AM2"})
        self.assertTrue(receipt["financial_apply_locked"])
        self.assertFalse(receipt["v218_real_monetary_parity_certified"])
    def test_25_no_model_copy_history_and_no_authorized_export(self):
        s=snapshot();b=CaptureBook()
        x=apply_locked_model_columns(b,s,plan(s))
        self.assertFalse(x["financial_statuses_certified"])
        self.assertEqual(x["all_bank_statuses"],"SUSPENSE")
        self.assertEqual(x["real_bank_allocations"],0)
        self.assertFalse(x["production_release_authorized"])
    def test_26_unknown_official_sol_does_not_fake(self):
        s=snapshot()
        s.master_pairs=(("0002","SYNTHETIC BETA"),)
        p,i=cells(s)
        self.assertIsNone(p[0][10])
        self.assertIsNone(i[0][0])
    def test_27_multiple_partials_no_double_published_invoice_credit(self):
        s=snapshot(
          payments=[pay(credit="500"),pay(source_row=3,credit="660")],
          pcount=2)
        from sbi_r267_readonly_real_candidate_engine import RelationshipProof
        q=[RelationshipProof(2,"MXP10001","PARTIAL","SYN-DOC-1",True),
           RelationshipProof(3,"MXP10001","PARTIAL","SYN-DOC-2",True)]
        r=plan_review_only(list(s.invoices),list(s.payments),list(s.master_pairs),
                           source_sha256=H,master_sha256=H,relationship_proofs=q)
        p,i=cells(s,r)
        self.assertEqual(len(p),2)
        self.assertIn("MULTIPLE PARTIAL CANDIDATES",i[0][4])
        self.assertIsNone(i[0][3])
    def test_28_header_constant_no_unapproved_status(self):
        self.assertNotIn("OK",PAYMENT_HEADERS[0])
    def test_29_all_source_original_columns_never_written_by_fake(self):
        s=snapshot();b=CaptureBook()
        apply_locked_model_columns(b,s,plan(s))
        self.assertNotIn("J2",repr(b.worksheets.items["Invoice Details."].cells))
        self.assertNotIn("I2",repr(b.worksheets.items["PAYMNENT"].cells))
    def test_30_do_not_allow_writer_source_row_outside_original(self):
        s=snapshot(payments=[pay(source_row=5)])
        with self.assertRaisesRegex(R267WriterRefusal,"PAYMENT_SOURCE_ROW_OUT_OF_BOUNDS"):
            cells(s)

if __name__=="__main__":unittest.main()
