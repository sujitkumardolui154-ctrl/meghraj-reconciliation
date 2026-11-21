"""Fabricated XLSX only: actual Stage4 new-source parse + signed ledger review."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib
import hmac
import json
import tempfile
import unittest

from artifact_tool import Workbook, SpreadsheetFile
from new_only_adapter import NewSourceBlocked, review_new_only_pair, _xl_snapshot
from sbi_engine.reference_schema import PAYMENT_HEADERS,INVOICE_HEADERS
from stage4_ledger import Principal, Stage4Blocked, Stage4Policy, upload_row_sha256

KEY=b'FAKE_TEST_ONLY_32_BYTES_LONG_NEVER_USE_IN_PRODUCTION'
POLICY=Stage4Policy('SBI_INTERNAL_GATEWAY_TEST','2026-11-21','2026-11-22',KEY)
UP=Principal('synthetic_up','INTAKE')
REVIEW=Principal('synthetic_reviewer','REVIEWER')
ROW={'Description':'SYNTHETIC NOVEMBER POSTAGE','SOL ID':'0001505','Credit Amount':'118.00'}

def sign(body,kind):
    raw=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    return hmac.new(KEY,b'SBI_STG4_V1:'+kind.encode()+b':'+raw,hashlib.sha256).hexdigest()

def fixture(path, *, paid_marker=None, extra_sheet=False, wrong_invoice_col=False, formula_credit=False):
    wb=Workbook.create()
    pay=wb.worksheets.add('PAYMNENT'); inv=wb.worksheets.add('Invoice Details.')
    pay.get_range('A1:L1').values=[list(PAYMENT_HEADERS)]
    inv.get_range('A1:AI1').values=[list(INVOICE_HEADERS)]
    pay.get_range('C2').values=[['2026-11-22']]
    pay.get_range('E2:G2').values=[[ROW['Description'],'0001505','SYNTHETIC CLIENT']]
    pay.get_range('H2:I2').values=[[0,118]]
    pay.get_range('J2').formulas=[['=I2-H2']]
    inv.get_range('E2:H2').values=[['2026-11','2026-11-21','0001505','SYNTHETIC CLIENT']]
    inv.get_range('K2:O2').values=[['SYNTH-INV-0001',100,9,9,118]]
    inv.get_range('I2').values=[['0001505']]
    if paid_marker is not None:inv.get_range('S2').values=[[paid_marker]]
    if wrong_invoice_col:
        inv.get_range('K2').values=[['BAD']]
        inv.get_range('J2').values=[['SYNTH-INV-0001']]
    if formula_credit: pay.get_range('I2').formulas=[['=100+18']]
    if extra_sheet:wb.worksheets.add('Historical Payments')
    SpreadsheetFile.export_xlsx(wb).save(str(path))


def evidence(path):
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    bank=dict(schema='SBI_BANK_EVIDENCE_V1',issuer=POLICY.issuer,
        source_kind='NEW_ONLY',source_sha256=h,source_row=2,
        source_column='PAYMNENT!I',statement_sha256=hashlib.sha256(b'FAKE statement').hexdigest(),
        bank_date='2026-11-22',payment_reference='SYNTH-UTR-0001',
        sol_id='0001505',client_name='SYNTHETIC CLIENT',
        upload_row_sha256=upload_row_sha256(ROW),description=ROW['Description'],
        credit_amount='118.00',invoice_reference='SYNTH-INV-0001',service_month='2026-11')
    inv=dict(schema='SBI_INVOICE_EVIDENCE_V1',issuer=POLICY.issuer,
        source_kind='NEW_ONLY',source_sha256=h,source_row=2,
        invoice_no='SYNTH-INV-0001',invoice_date='2026-11-21',
        sol_id='0001505',client_name='SYNTHETIC CLIENT',service_month='2026-11',
        taxable='100.00',cgst='9.00',sgst='9.00',gross='118.00',
        paid_marker='',credit_note=False)
    return bank,inv

class WorkbookIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='SBI_STAGE43_FAKE_');self.addCleanup(self.temp.cleanup)
        self.src=Path(self.temp.name)/'SYNTHETIC_NEWONLY_SOURCE.xlsx'
        fixture(self.src)
        self.bank,self.inv=evidence(self.src)

    def run_review(self, **kw):
        params={'source_xlsx':self.src,'payment_row':ROW,
                'bank_evidence':self.bank,'bank_tag':sign(self.bank,'bank'),
                'invoice_evidence':self.inv,'invoice_tag':sign(self.inv,'invoice'),
                'policy':POLICY,'uploader':UP,'reviewer':REVIEW}
        params.update(kw)
        return review_new_only_pair(**params)

    def test_valid_two_sheet_new_format_review_no_writes(self):
        before=self.src.read_bytes()
        result=self.run_review()
        self.assertEqual(self.src.read_bytes(),before)
        self.assertEqual(result['status'],'SYNTHETIC_NEW_ONLY_SOURCE_REVIEWED_NOT_RECONCILED')
        self.assertFalse(result['bank_origin_independently_authenticated'])
        self.assertFalse(result['output_writer_legacy_v218_compatible'])
        self.assertEqual(result['candidate_reservations'],0)
        self.assertEqual(result['legacy_v218_export'],'BLOCKED_SOURCE_COLUMN_OVERLAP')
        self.assertFalse(result['financial_writes'])
        self.assertTrue(result['receipt_reviewed'])

    def test_readonly_parser_matches_real_excel_k_and_o(self):
        tabs,sheets=_xl_snapshot(self.src)
        self.assertEqual(tabs,('PAYMNENT','Invoice Details.'))
        self.assertEqual(sheets['Invoice Details.'][(2,11)][1],'SYNTH-INV-0001')
        self.assertEqual(sheets['Invoice Details.'][(2,15)][1],'118')
        self.assertEqual(sheets['PAYMNENT'][(2,6)][1],'0001505')
        self.assertEqual(sheets['PAYMNENT'][(2,10)][2],'I2-H2')

    def test_unapproved_real_filename_denied(self):
        renamed=Path(self.temp.name)/'BankStatement.xlsx'
        renamed.write_bytes(self.src.read_bytes())
        with self.assertRaisesRegex(NewSourceBlocked,'SYNTHETIC_TWO_SHEET_FILE_ONLY'):
            self.run_review(source_xlsx=renamed)

    def test_post_signature_file_tampering_denied(self):
        fixture(self.src,paid_marker=0)
        with self.assertRaisesRegex(NewSourceBlocked,'SIGNED_WORKBOOK_SHA256_CONFLICT'):
            self.run_review()

    def test_bad_internal_gateway_tag_denied(self):
        with self.assertRaisesRegex(Stage4Blocked,'ATTESTATION_SIGNATURE_MISMATCH'):
            self.run_review(bank_tag='0'*64)

    def test_bad_invoice_internal_gateway_tag_denied(self):
        with self.assertRaisesRegex(Stage4Blocked,'ATTESTATION_SIGNATURE_MISMATCH'):
            self.run_review(invoice_tag='0'*64)

    def test_changed_unsigned_upload_row_denied(self):
        changed={**ROW,'Credit Amount':'119.00'}
        with self.assertRaisesRegex(NewSourceBlocked,'UPLOAD_ROW_SOURCE_CONFLICT'):
            self.run_review(payment_row=changed)

    def test_numeric_zero_paid_marker_denied(self):
        fixture(self.src,paid_marker=0)
        self.bank,self.inv=evidence(self.src)
        with self.assertRaisesRegex(NewSourceBlocked,'PAID_MARKER_NONBLANK_INCLUDING_ZERO'):
            self.run_review()

    def test_legacy_invoice_number_column_j_denied(self):
        fixture(self.src,wrong_invoice_col=True)
        self.bank,self.inv=evidence(self.src)
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_INVOICE_NO_SOURCE_CONFLICT'):
            self.run_review()

    def test_formula_credit_i_denied(self):
        fixture(self.src,formula_credit=True)
        self.bank,self.inv=evidence(self.src)
        with self.assertRaisesRegex(NewSourceBlocked,'SOURCE_CELL_MISSING_OR_FORMULA_2_9'):
            self.run_review()

    def test_extra_sheet_denied(self):
        fixture(self.src,extra_sheet=True)
        self.bank,self.inv=evidence(self.src)
        with self.assertRaisesRegex(NewSourceBlocked,'EXACT_TWO_SOURCE_SHEETS_REQUIRED'):
            self.run_review()

    def test_cross_source_wrong_sol_denied_even_when_resigned(self):
        self.inv['sol_id']='0001506'
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_SOL_ID_SOURCE_CONFLICT'):
            self.run_review()

    def test_wrong_reviewer_role_denied(self):
        with self.assertRaisesRegex(NewSourceBlocked,'DISTINCT_TRUSTED_HOST_ROLES_REQUIRED'):
            self.run_review(reviewer=UP)

if __name__=='__main__':unittest.main()
