"""R26.6 synthetic tiny XLSX fixtures for real-source read-only preflight.

All test invoices are SYN- identifiers. NO actual SBI source bytes in CI.
Build XLSX using stdlib ZIP/XML without a financial writer dependency.
"""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r266_readonly_real_source_population_gate import (
    R266Refusal, scan_readonly_source, compare_readonly_snapshots,
)


def cell(ref, value, typ=None):
    if value is None:
        return ""
    if typ == "e":
        return f'<c r="{ref}" t="e"><v>{escape(str(value))}</v></c>'
    if isinstance(value,str):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    return f'<c r="{ref}"><v>{value}</v></c>'


def invoice_head():
    return ''.join(cell(col+"1",v) for col,v in (
        ("G","Branch Code"),("H","Client Name"),("J","Invoice No"),
        ("K","Taxable Amount"),("L","CGST"),("M","SGST"),
        ("N","Total Bill Amount"),
    ))


def bank_head():
    return (cell("C1","Txn Date")+cell("E1","Description")+cell("F1","Branch Code")+cell("G1","Name")+cell("I1","Credit")+cell("K1","Record For Me"))


def inv(number=2, key="SYN-MXP-001", sol="0001", taxable=1000,
        cgst=90, sgst=90, gross=1180, tds=20,
        receivable=1160, net_taxable=980, protected=None,
        sgst_type=None):
    parts=(
        cell(f"G{number}",sol)+cell(f"H{number}","SYNTHETIC ALPHA")
        +cell(f"J{number}",key)+cell(f"K{number}",taxable)
        +cell(f"L{number}",cgst)+cell(f"M{number}",sgst,typ=sgst_type)
        +cell(f"N{number}",gross)+cell(f"O{number}",tds)
        +cell(f"P{number}",receivable)+cell(f"Q{number}",net_taxable)
        +cell(f"S{number}",protected)
    )
    return f'<row r="{number}">{parts}</row>'


def bank(number=2, credit=1160, sol="0001"):
    parts=cell(f"F{number}",sol)+cell(f"I{number}",credit)
    return f'<row r="{number}">{parts}</row>'


def workbook(invoice_rows=None, bank_rows=None, invoice_header=None,
             payment_header=None, extra_sheets=False):
    if invoice_rows is None:
        invoice_rows=[inv()]
    if bank_rows is None:
        bank_rows=[bank()]
    ih=invoice_head() if invoice_header is None else invoice_header
    bh=bank_head() if payment_header is None else payment_header
    xm='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    root='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    ws=lambda h,rows:f'{xm}<worksheet xmlns="{root}"><sheetData><row r="1">{h}</row>{"".join(rows)}</sheetData></worksheet>'
    relns='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    names=[("Invoice Details.","sheet1.xml"),("PAYMNENT","sheet2.xml")]
    if extra_sheets:names.append(("OTHER","sheet3.xml"))
    book=f'{xm}<workbook xmlns="{root}" xmlns:r="{relns}"><sheets>'+''.join(
        f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>'
        for i,(n,_) in enumerate(names,1)
    )+'</sheets></workbook>'
    relation=f'{xm}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(
        f'<Relationship Id="rId{i}" Type="{relns}/worksheet" Target="worksheets/{p}"/>'
        for i,(_,p) in enumerate(names,1)
    )+'</Relationships>'
    files={
        'xl/workbook.xml':book,
        'xl/_rels/workbook.xml.rels':relation,
        'xl/worksheets/sheet1.xml':ws(ih,invoice_rows),
        'xl/worksheets/sheet2.xml':ws(bh,bank_rows),
    }
    if extra_sheets:files['xl/worksheets/sheet3.xml']=ws("",[])
    stream=BytesIO()
    with ZipFile(stream,'w',ZIP_DEFLATED) as z:
        for path,txt in files.items():z.writestr(path,txt)
    return stream.getvalue()


def scan(contents,**opts):
    return scan_readonly_source(contents,expected_sha256=sha256(contents).hexdigest(),**opts)


def compare(source,clean,**opts):
    return compare_readonly_snapshots(
        source,clean,
        expected_original_sha256=sha256(source).hexdigest(),
        expected_cleaned_sha256=sha256(clean).hexdigest(),
        **opts,
    )


class R266ReadOnlyRealSourceGateTests(unittest.TestCase):
    def test_01_invoice_count(self):
        self.assertEqual(scan(workbook())['invoice_data_rows'],1)
    def test_02_payment_count(self):
        self.assertEqual(scan(workbook())['payment_data_rows'],1)
    def test_03_bank_positive_credit_is_I_only(self):
        self.assertEqual(scan(workbook())['positive_bank_credit_rounded_sum'],'1160.00')
    def test_04_invoice_gross_from_N_not_SGST(self):
        self.assertEqual(scan(workbook())['gross_cached_rounded_sum'],'1180.00')
    def test_05_invoice_taxable_from_K(self):
        self.assertEqual(scan(workbook())['taxable_cached_rounded_sum'],'1000.00')
    def test_06_tds_does_not_set_bank_paid_status(self):
        r=scan(workbook())
        self.assertFalse(r['historical_OK_status_copy_authorized'])
        self.assertFalse(r['complete_master_v251_matrix_v239_certified'])
    def test_07_no_allocation_or_production_writes(self):
        r=scan(workbook())
        self.assertTrue(r['financial_apply_locked'])
        self.assertFalse(r['reconciliation_allocation_executed'])
        self.assertEqual(r['production_database_writes'],0)
    def test_08_source_sha_mismatch_refused(self):
        with self.assertRaisesRegex(R266Refusal,'SOURCE_SHA256_MISMATCH'):
            scan_readonly_source(workbook(),expected_sha256='f'*64)
    def test_09_missing_hash_format_refused(self):
        with self.assertRaisesRegex(R266Refusal,'SOURCE_SHA256_REQUIRED'):
            scan_readonly_source(workbook(),expected_sha256='bad')
    def test_10_unlock_financial_apply_refused(self):
        with self.assertRaisesRegex(R266Refusal,'FINANCIAL_APPLY_LOCK_REQUIRED'):
            scan(workbook(),financial_apply='ENABLED')
    def test_11_duplicate_invoice_group_flagged(self):
        d=scan(workbook(invoice_rows=[
            inv(),inv(3,key="SYN-MXP-001")]))
        self.assertEqual(d['findings']['duplicate_invoice_groups'],1)
        self.assertEqual(d['findings']['duplicate_invoice_rows'],2)
    def test_12_blank_invoice_identity_does_not_create_duplicate(self):
        d=scan(workbook(invoice_rows=[
            inv(key=""),inv(3,key="")]))
        self.assertEqual(d['findings'].get('duplicate_invoice_groups',0),0)
    def test_13_negative_credit_note_like_gross_is_not_discarded(self):
        d=scan(workbook(invoice_rows=[inv(),inv(3,key="SYN-MXP-002",
            taxable=-20,cgst=0,sgst=0,gross=-20,tds=0,
            receivable=-20,net_taxable=-20)]))
        self.assertEqual(d['gross_cached_rounded_sum'],'1160.00')
        self.assertEqual(d['findings']['negative_gross_credit_note_like_rows'],1)
    def test_14_remove_negative_row_increases_gross_and_requires_review(self):
        source=workbook(invoice_rows=[
            inv(),inv(3,key="SYN-MXP-002",taxable=-20,cgst=0,
                      sgst=0,gross=-20,tds=0,receivable=-20,net_taxable=-20)])
        clean=workbook()
        r=compare(source,clean)
        self.assertEqual(r['gross_total_difference_clean_minus_original'],'20.00')
        self.assertTrue(r['negative_removed_invoice_net_gross_suspected'])
        self.assertEqual(r['decision'],'SOURCE_REVIEW_REQUIRED_NOT_FINANCIAL_SETTLEMENT')
    def test_15_nonnumeric_bank_credit_counted_not_payment(self):
        d=scan(workbook(bank_rows=[bank(),bank(3,"Credit")]))
        self.assertEqual(d['findings']['bank_credit_non_numeric'],1)
        self.assertEqual(d['positive_bank_credit_rounded_sum'],'1160.00')
    def test_16_remove_nonnumeric_header_bank_credit_does_not_reduce_cash(self):
        source=workbook(bank_rows=[bank(),bank(3,'Credit')])
        clean=workbook()
        r=compare(source,clean)
        self.assertTrue(r['positive_bank_credit_total_same'])
        self.assertEqual(r['excluded_payment_row_count'],1)
    def test_17_bank_credit_blank_not_payment(self):
        d=scan(workbook(bank_rows=[bank(2,None)]))
        self.assertEqual(d['findings']['bank_credit_blank'],1)
    def test_18_zero_credit_not_positive(self):
        d=scan(workbook(bank_rows=[bank(2,0)]))
        self.assertEqual(d['findings']['bank_credit_zero'],1)
    def test_19_negative_bank_credit_not_in_positive_total(self):
        d=scan(workbook(bank_rows=[bank(2,-10)]))
        self.assertEqual(d['findings']['bank_credit_negative'],1)
        self.assertEqual(d['positive_bank_credit_rounded_sum'],'0.00')
    def test_20_cached_float_precision_rounds_at_paise(self):
        d=scan(workbook(bank_rows=[bank(2,31.86000000000001)]))
        self.assertEqual(d['positive_bank_credit_rounded_sum'],'31.86')
    def test_21_gross_tax_component_mismatch_review(self):
        d=scan(workbook(invoice_rows=[inv(gross=1200)]))
        self.assertEqual(d['findings']['invoice_gross_component_mismatch_over_cent'],1)
    def test_22_receivable_tds_mismatch_review(self):
        d=scan(workbook(invoice_rows=[inv(receivable=1150)]))
        self.assertEqual(d['findings']['invoice_receivable_after_tds_mismatch_over_cent'],1)
    def test_23_net_taxable_tds_mismatch_review(self):
        d=scan(workbook(invoice_rows=[inv(net_taxable=970)]))
        self.assertEqual(d['findings']['invoice_net_taxable_after_tds_mismatch_over_cent'],1)
    def test_24_non_numeric_sgst_is_not_coerced_to_zero(self):
        d=scan(workbook(invoice_rows=[inv(sgst="OK")]))
        self.assertEqual(d['findings']['invoice_core_amount_non_numeric'],1)
    def test_25_cached_excel_error_is_not_a_numeric_amount(self):
        d=scan(workbook(invoice_rows=[inv(sgst="#VALUE!",sgst_type="e")]))
        self.assertEqual(d['findings']['invoice_cached_formula_errors'],1)
        self.assertEqual(d['findings']['invoice_core_amount_non_numeric'],1)
    def test_26_original_invoice_S_nonblank_protected(self):
        d=scan(workbook(invoice_rows=[inv(protected='2026-09-20')]))
        self.assertEqual(d['findings']['original_s_protected_nonblank'],1)
    def test_27_original_invoice_S_numeric_zero_protected(self):
        d=scan(workbook(invoice_rows=[inv(protected=0)]))
        self.assertEqual(d['findings']['original_s_protected_nonblank'],1)
    def test_28_numeric_SOL_is_flagged_not_autopadded(self):
        d=scan(workbook(invoice_rows=[inv(sol=1)]))
        self.assertEqual(d['findings']['invoice_sol_not_text'],1)
    def test_29_text_SOL_leading_zeros_unmodified(self):
        d=scan(workbook(invoice_rows=[inv(sol='0001')]))
        self.assertEqual(d['findings'].get('invoice_sol_not_text',0),0)
    def test_30_invoice_J_mapping_header_mismatch_refused(self):
        header=invoice_head().replace("Invoice No","SGST")
        with self.assertRaisesRegex(R266Refusal,"ORIGINAL_INVOICE_J_TO_N_CONTRACT_FAILED"):
            scan(workbook(invoice_header=header))
    def test_31_invoice_M_sgst_header_mismatch_refused(self):
        header=invoice_head().replace(">SGST<",">Invoice No<")
        with self.assertRaisesRegex(R266Refusal,"ORIGINAL_INVOICE_J_TO_N_CONTRACT_FAILED"):
            scan(workbook(invoice_header=header))
    def test_32_payment_I_credit_header_mismatch_refused(self):
        with self.assertRaisesRegex(R266Refusal,"ORIGINAL_BANK_CREDIT_I_CONTRACT_FAILED"):
            scan(workbook(payment_header=bank_head().replace("Credit","Debit")))
    def test_33_invalid_archive_refused(self):
        bad=b'fake non xlsx'
        with self.assertRaisesRegex(R266Refusal,"INVALID_OR_UNSUPPORTED_XLSX_ARCHIVE"):
            scan_readonly_source(bad,expected_sha256=sha256(bad).hexdigest())
    def test_34_no_bank_source_leak_in_summary(self):
        d=scan(workbook())
        self.assertNotIn('SYN-MXP-001',repr(d))
        self.assertNotIn('SYNTHETIC ALPHA',repr(d))
    def test_35_cleaned_population_more_invoice_rows_fails_closed(self):
        with self.assertRaisesRegex(R266Refusal,"CLEANED_POPULATION_EXCEEDS_ORIGINAL"):
            compare(workbook(),workbook(invoice_rows=[inv(),inv(3,key="SYN-MXP-002")]))
    def test_36_cleaned_population_more_bank_rows_fails_closed(self):
        with self.assertRaisesRegex(R266Refusal,"CLEANED_POPULATION_EXCEEDS_ORIGINAL"):
            compare(workbook(),workbook(bank_rows=[bank(),bank(3,10)]))
    def test_37_removed_positive_credit_not_declared_preserved(self):
        r=compare(workbook(bank_rows=[bank(),bank(3,100)]),workbook())
        self.assertFalse(r['positive_bank_credit_total_same'])
    def test_38_same_workbook_safe_self_compare_not_a_finance_approval(self):
        book=workbook()
        r=compare(book,book)
        self.assertEqual(r['excluded_payment_row_count'],0)
        self.assertEqual(r['excluded_invoice_row_count'],0)
        self.assertFalse(r['real_bank_ledger_statuses_authorized'])
        self.assertFalse(r['real_v218_financial_writer_parity_verified'])
    def test_39_extra_sheets_do_not_change_original_contract(self):
        d=scan(workbook(extra_sheets=True))
        self.assertEqual(d['invoice_data_rows'],1)
    def test_40_no_full_engine_certification_path(self):
        book=workbook()
        d=compare(book,book)
        self.assertFalse(d['formula_recalculation_parity_verified'])
        self.assertFalse(d['all_exclusion_owner_decisions_verified'])
        self.assertTrue(d['financial_apply_locked'])
        self.assertEqual(d['production_database_writes'],0)


if __name__=="__main__":
    unittest.main()
