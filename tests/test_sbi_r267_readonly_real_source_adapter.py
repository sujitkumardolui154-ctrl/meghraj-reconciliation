"""R26.7 original-SBI-column adapter: synthetic ZIP/XML tests only."""
import io,sys,unittest,zipfile
from pathlib import Path
from hashlib import sha256
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from test_sbi_r266_readonly_real_source_population_gate import (
    workbook,invoice_head,bank_head,cell,
)
from sbi_r267_readonly_real_source_adapter import (
    excel_date,service_months,read_private_snapshots,sanitized_receipt,
)
from sbi_r267_readonly_real_candidate_engine import (
    plan_review_only,FinancialReviewRefusal,
)

def invoice(row=2,**kw):
    x=dict(sol="0001",key="MXP10001",client="SYNTHETIC ALPHA",
           period="2026-09",invoice_date="2026-09-01",
           taxable=1000,cgst=90,sgst=90,gross=1180,s="")
    x.update(kw)
    values=[
        ("E",x["period"]),("F",x["invoice_date"]),("G",x["sol"]),
        ("H",x["client"]),("J",x["key"]),("K",x["taxable"]),
        ("L",x["cgst"]),("M",x["sgst"]),("N",x["gross"]),
        ("S",x["s"]),
    ]
    return f'<row r="{row}">'+''.join(
        cell(f'{k}{row}',v) for k,v in values)+'</row>'

def bankrow(row=2,**kw):
    x=dict(sol="0001",client="SYNTHETIC ALPHA",
           description="POSTAGE MXP10001 SEPTEMBER 2026",
           bank_date="2026-09-15",credit=1160,k="")
    x.update(kw)
    values=[
        ("C",x["bank_date"]),("E",x["description"]),("F",x["sol"]),
        ("G",x["client"]),("I",x["credit"]),("K",x["k"])
    ]
    return f'<row r="{row}">'+''.join(
        cell(f'{k}{row}',v) for k,v in values)+'</row>'

def tiny_source(invrows=None,payrows=None):
    return workbook(
        invoice_rows=[invoice()] if invrows is None else invrows,
        bank_rows=[bankrow()] if payrows is None else payrows,
    )

def tiny_master(official="SYNTHETIC ALPHA",sol="0001",valid=True):
    base=workbook(extra_sheets=True)
    other=[]
    with zipfile.ZipFile(io.BytesIO(base)) as z:
        for n in z.namelist():
            payload=z.read(n)
            if n=="xl/workbook.xml":
                payload=payload.replace(b'name="OTHER"',b'name="Clean Branch Master"')
            if n=="xl/worksheets/sheet3.xml":
                row='<row r="1">'+cell("B1","Official Branch Name")
                row+=cell("D1","SOL ID" if valid else "NOT_SOL")+'</row>'
                row2='<row r="2">'+cell("B2",official)+cell("D2",sol)+'</row>'
                payload=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                      '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                      '<sheetData>'+row+row2+'</sheetData></worksheet>').encode()
            other.append((n,payload))
    target=io.BytesIO()
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as z:
        for n,p in other:z.writestr(n,p)
    return target.getvalue()

def read(src=None,master=None):
    src=tiny_source() if src is None else src
    master=tiny_master() if master is None else master
    return read_private_snapshots(
        src,master,
        source_sha256=sha256(src).hexdigest(),
        master_sha256=sha256(master).hexdigest(),
    )

class R267AdapterTests(unittest.TestCase):
    def test_01_two_sheets_and_master_import(self):
        r=read()
        self.assertEqual(len(r.invoices),1)
        self.assertEqual(len(r.payments),1)
        self.assertEqual(len(r.master_pairs),1)
    def test_02_source_serial_month_preserved(self):
        r=read(tiny_source(invrows=[invoice(period="45717")]))
        self.assertEqual(r.invoices[0].service_periods,("2025-03",))
    def test_03_iso_service_period_preserved(self):
        self.assertEqual(service_months("2026-09"),("2026-09",))
    def test_04_month_name_year_parsed(self):
        self.assertEqual(service_months("September 2026"),("2026-09",))
    def test_05_mar_to_may_multimonth_parsed(self):
        self.assertEqual(service_months("March to May2026"),
                         ("2026-03","2026-04","2026-05"))
    def test_06_aug_two_digit_year(self):
        self.assertEqual(service_months("AUG-26"),("2026-08",))
    def test_07_numeric_month_year(self):
        self.assertEqual(service_months("08-2026"),("2026-08",))
    def test_08_payment_narration_mxp_only_not_period(self):
        self.assertEqual(service_months("MXP10001"),())
    def test_09_service_month_not_inferred_from_posting_date(self):
        r=read(tiny_source(payrows=[
            bankrow(description="POSTAGE MXP10001")]))
        self.assertEqual(r.payments[0].service_periods,())
    def test_10_invoice_issue_date_parse(self):
        self.assertEqual(read().invoices[0].issue_date,date(2026,9,1))
    def test_11_bank_date_parse(self):
        self.assertEqual(read().payments[0].bank_date,date(2026,9,15))
    def test_12_original_paid_s_nonblank_preserved(self):
        r=read(tiny_source(invrows=[invoice(s=0)]))
        self.assertEqual(r.invoices[0].original_s,"0")
    def test_13_original_payment_k_nonblank_preserved(self):
        r=read(tiny_source(payrows=[bankrow(k="OK")]))
        self.assertEqual(r.payments[0].original_k,"OK")
    def test_14_negative_gross_retained_for_quarantine(self):
        r=read(tiny_source(invrows=[
            invoice(taxable=-100,cgst=-9,sgst=-9,gross=-118)]))
        self.assertEqual(r.invoices[0].gross,"-118.00")
    def test_15_invalid_gross_cached_error_quarantined(self):
        r=read(tiny_source(invrows=[invoice(gross="#VALUE!")]))
        self.assertFalse(r.invoices)
        self.assertIn(("INVOICE",2,"INVOICE_CORE_MONEY_NONNUMERIC"),
                      r.review_only_hold_codes)
    def test_16_numeric_sol_invoice_quarantined(self):
        r=read(tiny_source(invrows=[invoice(sol=1)]))
        self.assertFalse(r.invoices)
        self.assertIn(("INVOICE",2,"NUMERIC_OR_MISSING_SOL_SOURCE_TYPE"),
                      r.review_only_hold_codes)
    def test_17_numeric_sol_payment_quarantined(self):
        r=read(tiny_source(payrows=[bankrow(sol=1)]))
        self.assertFalse(r.payments)
        self.assertIn(("PAYMENT",2,"BANK_SOL_NOT_TEXT"),
                      r.review_only_hold_codes)
    def test_18_nonnumeric_bank_credit_skipped(self):
        r=read(tiny_source(payrows=[bankrow(credit="Credit")]))
        self.assertFalse(r.payments)
        self.assertIn(("PAYMENT",2,"BANK_CREDIT_BLANK_OR_NONNUMERIC"),
                      r.review_only_hold_codes)
    def test_19_blank_bank_credit_skipped(self):
        r=read(tiny_source(payrows=[bankrow(credit=None)]))
        self.assertFalse(r.payments)
    def test_20_source_same_invoice_j(self):
        self.assertEqual(read().invoices[0].invoice_no,"MXP10001")
    def test_21_gst_m_not_invoice_no(self):
        self.assertEqual(read().invoices[0].sgst,"90.00")
    def test_22_credit_only_column_i(self):
        self.assertEqual(read().payments[0].credit,"1160.00")
    def test_23_private_receipt_no_identifying_values(self):
        r=sanitized_receipt(read())
        self.assertNotIn("SYNTHETIC ALPHA",repr(r))
        self.assertNotIn("MXP10001",repr(r))
        self.assertFalse(r["output_statuses_not_certified"] is False)
    def test_24_bad_master_header_refused(self):
        with self.assertRaisesRegex(FinancialReviewRefusal,"OFFICIAL_MASTER_HEADER_MISMATCH"):
            read(master=tiny_master(valid=False))
    def test_25_numeric_master_sol_held(self):
        r=read(master=tiny_master(sol=1))
        self.assertEqual(r.master_pairs,())
        self.assertEqual(r.selected_master_invalid_sol_rows,1)
    def test_26_wrong_master_sha_refused(self):
        src=tiny_source();master=tiny_master()
        with self.assertRaisesRegex(FinancialReviewRefusal,"MASTER_SHA256_MISMATCH"):
            read_private_snapshots(src,master,source_sha256=sha256(src).hexdigest(),
                                    master_sha256="0"*64)
    def test_27_wrong_source_sha_refused(self):
        src=tiny_source();master=tiny_master()
        with self.assertRaisesRegex(FinancialReviewRefusal,"SOURCE_SHA256_MISMATCH"):
            read_private_snapshots(src,master,source_sha256="0"*64,
                                    master_sha256=sha256(master).hexdigest())
    def test_28_financial_apply_lock_refused(self):
        src=tiny_source();master=tiny_master()
        with self.assertRaisesRegex(FinancialReviewRefusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            read_private_snapshots(src,master,source_sha256=sha256(src).hexdigest(),
                                    master_sha256=sha256(master).hexdigest(),
                                    financial_apply="ENABLED")
    def test_29_adapter_and_review_planner_connected(self):
        r=read()
        x=plan_review_only(list(r.invoices),list(r.payments),
            list(r.master_pairs),source_sha256=r.source_sha256,
            master_sha256=r.master_sha256)
        self.assertEqual(x["candidate_rows"][0][3],"EXACT_MXP_TDS_REVIEW")
        self.assertTrue(x["financial_apply_locked"])
        self.assertEqual(x["real_database_writes"],0)
    def test_30_wrong_invoice_s_protected_in_connected_review(self):
        r=read(tiny_source(invrows=[invoice(s=0)]))
        x=plan_review_only(list(r.invoices),list(r.payments),
            list(r.master_pairs),source_sha256=r.source_sha256,
            master_sha256=r.master_sha256)
        self.assertEqual(len(x["candidate_rows"]),0)
    def test_31_wrong_official_client_name_unmatched(self):
        r=read(master=tiny_master(official="SYNTHETIC OTHER"))
        x=plan_review_only(list(r.invoices),list(r.payments),
            list(r.master_pairs),source_sha256=r.source_sha256,
            master_sha256=r.master_sha256)
        self.assertEqual(x["candidate_rows"],())
    def test_32_schema_wrong_original_payment_credit_header(self):
        src=tiny_source()
        with zipfile.ZipFile(io.BytesIO(src)) as z:
            entries=[(n,z.read(n)) for n in z.namelist()]
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
            for n,data in entries:
                if n=="xl/worksheets/sheet2.xml":
                    data=data.replace(b'>Credit<',b'>Debit<')
                z.writestr(n,data)
        with self.assertRaisesRegex(ValueError,"ORIGINAL_BANK_CREDIT_I_CONTRACT_FAILED"):
            read(bio.getvalue())

if __name__=="__main__":unittest.main()
