"""Fabricated only. Stage 4.2–4.5 source->candidate-review->v2.18 E2E."""
from __future__ import annotations

from pathlib import Path
import hashlib
import hmac
import json
import tempfile
import unittest
import sys

from artifact_tool import Blob, Workbook, SpreadsheetFile

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from combined_review import CombinedReviewBlocked, run_combined_review
from stage4_ledger import Principal, Stage4Blocked, Stage4Policy, upload_row_sha256
from v218_writer import _read_snap, _protected

KEY=b'ONLY_FABRICATED_STAGE42_COMBINED_QA_SECRET_2026'
UP=Principal('synthetic_intake','INTAKE')
REVIEW=Principal('synthetic_reviewer','REVIEWER')
POLICY=Stage4Policy('SBI_INTERNAL_GATEWAY_TEST','2026-11-21','2026-11-22',KEY)
H=lambda t:hashlib.sha256(t.encode()).hexdigest()
MANIFEST=json.loads((BASE/'references/V218_OUTPUT_HEADER_LOCK_MANIFEST.json').read_text('utf8'))

def sign(body,kind):
    raw=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    return hmac.new(KEY,b'SBI_STG4_V1:'+kind.encode()+b':'+raw,hashlib.sha256).hexdigest()


def fixture(path):
    wb=Workbook.create()
    for name in MANIFEST['sheets']:
        wb.worksheets.add(name)
    p=wb.worksheets.get_item('PAYMNENT')
    i=wb.worksheets.get_item('Invoice Details.')
    p.get_range('A1:L1').values=[[MANIFEST['headers']['PAYMNENT'][str(n)] for n in range(1,13)]]
    i.get_range('A1:AH1').values=[[MANIFEST['headers']['Invoice Details.'][str(n)] for n in range(1,35)]]
    p.get_range('C2').values=[['2026-11-22']]
    p.get_range('E2:G2').values=[['SYNTH POSTAGE NOV 2026','1505','DEMO CLIENT']]
    p.get_range('H2:I2').values=[[0,118]]
    p.get_range('J2').formulas=[['=I2-H2']]
    i.get_range('E2:H2').values=[['2026-11','2026-11-21','1505','DEMO CLIENT']]
    i.get_range('J2:N2').values=[['SYNTH-INV-0001',100,9,9,118]]
    wb.worksheets.get_item('mail').get_range('B2').formulas=[['=3*4']]
    SpreadsheetFile.export_xlsx(wb).save(str(path))


def evidence(src):
    digest=hashlib.sha256(Path(src).read_bytes()).hexdigest()
    row={'Description':'SYNTH POSTAGE NOV 2026','SOL ID':'1505','Credit Amount':'118.00'}
    bank=dict(schema='SBI_BANK_EVIDENCE_V1',issuer=POLICY.issuer,source_kind='NEW_ONLY',
              source_sha256=digest,source_row=2,source_column='PAYMNENT!I',
              statement_sha256=H('FAKE_BANK_STATEMENT'),bank_date='2026-11-22',
              payment_reference='SYNTH-UTR-0001',sol_id='1505',client_name='DEMO CLIENT',
              upload_row_sha256=upload_row_sha256(row),description=row['Description'],
              credit_amount='118.00',invoice_reference='SYNTH-INV-0001',
              service_month='2026-11')
    invoice=dict(schema='SBI_INVOICE_EVIDENCE_V1',issuer=POLICY.issuer,source_kind='NEW_ONLY',
                 source_sha256=digest,source_row=2,invoice_no='SYNTH-INV-0001',
                 invoice_date='2026-11-21',sol_id='1505',client_name='DEMO CLIENT',
                 service_month='2026-11',taxable='100.00',cgst='9.00',sgst='9.00',
                 gross='118.00',paid_marker='',credit_note=False)
    return row,bank,invoice

class CombinedReviewIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=Path(self.t.name)
        self.src=self.path/'SYNTHETIC_V218_SOURCE.xlsx'
        self.out=self.path/'SYNTHETIC_V218_REVIEW.xlsx'
        fixture(self.src)
        self.row,self.bank,self.inv=evidence(self.src)

    def run_bridge(self, **overrides):
        params=dict(source_xlsx=self.src,output_xlsx=self.out,
                    payment_row=self.row,bank_evidence=self.bank,bank_tag=sign(self.bank,'bank'),
                    invoice_evidence=self.inv,invoice_tag=sign(self.inv,'invoice'),
                    policy=POLICY,uploader=UP,reviewer=REVIEW)
        params.update(overrides)
        return run_combined_review(**params)

    def test_01_full_combined_source_to_ledger_to_xlsx_and_no_writes(self):
        before=_protected(_read_snap(self.src))
        x=self.run_bridge()
        after=_read_snap(self.out)
        self.assertEqual(before,_protected(after))
        self.assertEqual(x['payment_model_status'],'SUSPENSE')
        self.assertEqual(x['candidate_reservations'],0)
        self.assertFalse(x['bank_origin_independently_authenticated'])
        self.assertFalse(x['financial_writes'])
        self.assertFalse(x['production_apply_enabled'])
        self.assertEqual(after[1]['PAYMNENT'][(2,13)][1],'SUSPENSE')
        self.assertEqual(after[1]['PAYMNENT'][(2,22)],('text','1505',None))
        self.assertEqual(after[1]['PAYMNENT'][(2,10)][2],'I2-H2')
        self.assertEqual(after[1]['mail'][(2,2)][2],'3*4')

    def test_02_reject_real_financial_filename(self):
        with self.assertRaisesRegex(CombinedReviewBlocked,'SYNTHETIC_SOURCE_ONLY'):
            self.run_bridge(source_xlsx=self.path/'real-bank.xlsx')
        self.assertFalse(self.out.exists())

    def test_03_source_sha_tamper_denied(self):
        p=SpreadsheetFile.import_xlsx(Blob.load(str(self.src)))
        p.worksheets.get_item('PAYMNENT').get_range('G2').values=[['CHANGED CLIENT']]
        SpreadsheetFile.export_xlsx(p).save(str(self.src))
        with self.assertRaisesRegex(CombinedReviewBlocked,'SIGNED_SOURCE_FILE_SHA_MISMATCH'):
            self.run_bridge()
        self.assertFalse(self.out.exists())

    def test_04_signed_bank_claim_wrong_credit_denied(self):
        self.bank['credit_amount']='119.00'
        with self.assertRaisesRegex(CombinedReviewBlocked,'BANK_CREDIT_I_SOURCE_CONFLICT'):
            self.run_bridge()
        self.assertFalse(self.out.exists())

    def test_05_bad_bank_signature_denied(self):
        with self.assertRaisesRegex(Stage4Blocked,'SIGNATURE_MISMATCH'):
            self.run_bridge(bank_tag='0'*64)
        self.assertFalse(self.out.exists())

    def test_06_paid_marker_zero_denied(self):
        self.inv['paid_marker']='0'
        with self.assertRaisesRegex(Stage4Blocked,'PAID_OR_CREDIT_NOTE'):
            self.run_bridge()

    def test_07_wrong_invoice_identity_denied(self):
        self.inv['invoice_no']='SYNTH-INV-OTHER'
        self.bank['invoice_reference']='SYNTH-INV-OTHER'
        with self.assertRaisesRegex(CombinedReviewBlocked,'INVOICE_REFERENCE_SOURCE_CONFLICT'):
            self.run_bridge()

    def test_08_wrong_sol_cross_source_denied(self):
        self.inv['sol_id']='1506'
        with self.assertRaisesRegex(CombinedReviewBlocked,'CROSS_SOURCE_SOL_CLIENT_PERIOD_CONFLICT'):
            self.run_bridge()

    def test_09_wrong_v218_header_variant_denied(self):
        p=SpreadsheetFile.import_xlsx(Blob.load(str(self.src)))
        p.worksheets.get_item('Invoice Details.').get_range('J1').values=[['Branch Code']]
        SpreadsheetFile.export_xlsx(p).save(str(self.src))
        # Resign source hash as if internal gateway saw the altered source. Still block layout.
        digest=hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.bank['source_sha256']=digest;self.inv['source_sha256']=digest
        with self.assertRaisesRegex(CombinedReviewBlocked,'UNAPPROVED_V218_SOURCE_LAYOUT'):
            self.run_bridge()
        self.assertFalse(self.out.exists())

    def test_10_no_unreviewed_or_same_user_role(self):
        with self.assertRaisesRegex(CombinedReviewBlocked,'DISTINCT_TEST_ROLES_REQUIRED'):
            self.run_bridge(reviewer=Principal(UP.uid,'REVIEWER'))

    def test_11_output_collision_does_not_change_old_output(self):
        self.out.write_bytes(b'EXISTING_NONFINANCIAL_TEST_OUTPUT')
        with self.assertRaisesRegex(CombinedReviewBlocked,'OUTPUT_ALREADY_EXISTS'):
            self.run_bridge()
        self.assertEqual(self.out.read_bytes(),b'EXISTING_NONFINANCIAL_TEST_OUTPUT')

    def test_12_bank_date_wrong_source_denied(self):
        self.bank['bank_date']='2026-11-21'
        with self.assertRaisesRegex(CombinedReviewBlocked,'BANK_DATE_SOURCE_CONFLICT'):
            self.run_bridge()

    def test_13_incorrect_credit_source_column_denied(self):
        self.bank['source_column']='PAYMNENT!H'
        with self.assertRaisesRegex(Stage4Blocked,'CREDIT_MUST_BE_COLUMN_I'):
            self.run_bridge()

    def test_14_bank_posted_before_invoice_date_denied(self):
        self.inv['invoice_date']='2026-11-22'
        self.bank['bank_date']='2026-11-21'
        with self.assertRaisesRegex(CombinedReviewBlocked,'INVOICE_DATE_SOURCE_CONFLICT|DATE_CHRONOLOGY_OR_180D_CONFLICT'):
            self.run_bridge()

    def test_15_gross_mismatch_denied(self):
        self.inv['gross']='119.00'
        with self.assertRaisesRegex(Stage4Blocked,'INVOICE_GROSS_MISMATCH'):
            self.run_bridge()

if __name__=='__main__':unittest.main()
