"""Pure Python new-format source layout and no-finance safety regression."""
from __future__ import annotations
from copy import deepcopy
from datetime import date
import unittest

from new_only_adapter import (NewSourceBlocked, snapshot_contract, column_index,
                              text_cell, amount_cell, SHEETS)
from sbi_engine.reference_schema import PAYMENT_HEADERS, INVOICE_HEADERS
from stage4_ledger import Stage4Policy, upload_row_sha256

POLICY = Stage4Policy('SBI_INTERNAL_GATEWAY_TEST', '2026-11-21','2026-11-22',
                      b'FAKE_TEST_ONLY_32_BYTES_LONG_NEVER_USE_IN_PRODUCTION')
ROW={'Description':'SYNTHETIC NOVEMBER POSTAGE', 'SOL ID':'0001505','Credit Amount':'118.00'}

def original():
    pay={(1,c):('text',v,None) for c,v in enumerate(PAYMENT_HEADERS,1)}
    invoice={(1,c):('text',v,None) for c,v in enumerate(INVOICE_HEADERS,1)}
    pay.update({(2,3):('text','2026-11-22',None),
                (2,5):('text',ROW['Description'],None),
                (2,6):('text','0001505',None),
                (2,9):('number','118',None)})
    invoice.update({(2,5):('text','2026-11',None),
                    (2,6):('text','2026-11-21',None),
                    (2,7):('text','0001505',None),
                    (2,8):('text','SYNTHETIC CLIENT',None),
                    (2,11):('text','SYNTH-INV-0001',None),
                    (2,12):('number','100.00',None),
                    (2,13):('number','9',None),
                    (2,14):('number','9.00',None),
                    (2,15):('number','118.00',None)})
    bank={'source_row':2,'source_sha256':'a'*64,
          'description':ROW['Description'], 'sol_id':'0001505',
          'bank_date':'2026-11-22', 'credit_amount':'118.00',
          'upload_row_sha256':upload_row_sha256(ROW),
          'invoice_reference':'SYNTH-INV-0001','client_name':'SYNTHETIC CLIENT',
          'service_month':'2026-11'}
    inv={'source_row':2,'source_sha256':'a'*64,
         'service_month':'2026-11','invoice_date':'2026-11-21',
         'sol_id':'0001505','client_name':'SYNTHETIC CLIENT',
         'invoice_no':'SYNTH-INV-0001','taxable':'100.00',
         'cgst':'9.00','sgst':'9.00','gross':'118.00'}
    return {SHEETS[0]:pay,SHEETS[1]:invoice},bank,inv

class NewFormatContractTests(unittest.TestCase):
    def setUp(self):
        self.s,self.b,self.i=original()

    def run_contract(self):
        return snapshot_contract(SHEETS,self.s,self.b,self.i,ROW,POLICY)

    def test_verified_new_headers_and_columns_are_non_legacy(self):
        result=self.run_contract()
        self.assertEqual(result['invoice_no_source_column'],'K')
        self.assertEqual(result['gross_source_column'],'O')
        self.assertFalse(result['output_writer_legacy_v218_compatible'])
        self.assertFalse(result['financial_writes'])
        self.assertFalse(result['bank_origin_independently_authenticated'])

    def test_leading_zero_sol_retained_as_text(self):
        self.assertEqual(text_cell(self.s[SHEETS[0]],2,6),'0001505')
        self.assertEqual(self.run_contract()['payment_row'],2)

    def test_invoice_number_old_column_j_is_not_used(self):
        self.s[SHEETS[1]][(2,10)]=('text','SYNTH-INV-0001',None)
        self.s[SHEETS[1]].pop((2,11))
        with self.assertRaisesRegex(NewSourceBlocked,'SOURCE_CELL_MISSING_OR_FORMULA_2_11'):
            self.run_contract()

    def test_wrong_header_position_denied(self):
        self.s[SHEETS[1]][(1,11)]=('text','Invoice Sequence',None)
        with self.assertRaisesRegex(NewSourceBlocked,'WRONG_INPUT_HEADER_COLUMN_11'):
            self.run_contract()

    def test_extra_sheet_denied(self):
        self.s['Extra']={}
        with self.assertRaisesRegex(NewSourceBlocked,'EXACT_TWO_SOURCE_SHEETS_REQUIRED'):
            snapshot_contract(SHEETS,self.s,self.b,self.i,ROW,POLICY)

    def test_payment_extra_column_denied(self):
        self.s[SHEETS[0]][(1,13)]=('text','Unauthorized Header',None)
        with self.assertRaisesRegex(NewSourceBlocked,'PAYMENT_SOURCE_EXTRA_COLUMN_FORBIDDEN'):
            self.run_contract()

    def test_invoice_extra_column_denied(self):
        self.s[SHEETS[1]][(1,36)]=('text','Unauthorized Header',None)
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_SOURCE_EXTRA_COLUMN_FORBIDDEN'):
            self.run_contract()

    def test_legacy_nine_tabs_denied(self):
        with self.assertRaisesRegex(NewSourceBlocked,'EXACT_TWO_SOURCE_SHEETS_REQUIRED'):
            snapshot_contract((*SHEETS,'mail'),self.s,self.b,self.i,ROW,POLICY)

    def test_bank_credit_column_h_is_not_i(self):
        self.s[SHEETS[0]][(2,8)]=('number','118',None)
        self.s[SHEETS[0]][(2,9)]=('number','0',None)
        with self.assertRaisesRegex(NewSourceBlocked,'BANK_CREDIT_I_SOURCE_CONFLICT'):
            self.run_contract()

    def test_invalid_row_credit_fraction_denied(self):
        self.s[SHEETS[0]][(2,9)]=('number','118.005',None)
        with self.assertRaisesRegex(NewSourceBlocked,'SOURCE_AMOUNT_NOT_EXACT_PAISE'):
            self.run_contract()

    def test_numeric_sol_unacceptable(self):
        self.s[SHEETS[0]][(2,6)]=('number','1505',None)
        with self.assertRaisesRegex(NewSourceBlocked,'SOURCE_TEXT_CELL_REQUIRED_2_6'):
            self.run_contract()

    def test_duplicate_invoice_row_denied(self):
        self.s[SHEETS[1]][(3,11)]=('text','SYNTH-INV-0002',None)
        with self.assertRaisesRegex(NewSourceBlocked,'SINGLE_NEW_ONLY_SYNTHETIC_PAIR_REQUIRED'):
            self.run_contract()

    def test_paid_marker_zero_is_not_blank(self):
        self.s[SHEETS[1]][(2,19)]=('number','0',None)
        with self.assertRaisesRegex(NewSourceBlocked,'PAID_MARKER_NONBLANK_INCLUDING_ZERO'):
            self.run_contract()

    def test_formula_disallowed_in_source_amount(self):
        self.s[SHEETS[1]][(2,15)]=('number','118', 'SUM(L2:N2)')
        with self.assertRaisesRegex(NewSourceBlocked,'SOURCE_CELL_MISSING_OR_FORMULA_2_15'):
            self.run_contract()

    def test_signed_period_mismatch_denied(self):
        self.i['service_month']='2026-10'
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_SERVICE_MONTH_SOURCE_CONFLICT'):
            self.run_contract()

    def test_wrong_invoice_client_denied(self):
        self.i['client_name']='DIFFERENT CLIENT'
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_CLIENT_NAME_SOURCE_CONFLICT'):
            self.run_contract()

    def test_upload_hash_mismatch_denied(self):
        self.b['upload_row_sha256']='0'*64
        with self.assertRaisesRegex(NewSourceBlocked,'UPLOAD_ROW_SOURCE_CONFLICT'):
            self.run_contract()

    def test_out_of_window_chronology_denied(self):
        self.s[SHEETS[0]][(2,3)]=('text','2027-10-01',None)
        self.b['bank_date']='2027-10-01'
        with self.assertRaisesRegex(NewSourceBlocked,'DATE_CHRONOLOGY_OR_180D_CONFLICT'):
            self.run_contract()

    def test_source_header_gross_position_o_required(self):
        self.s[SHEETS[1]][(2,15)]=('number','117.99',None)
        with self.assertRaisesRegex(NewSourceBlocked,'INVOICE_GROSS_AMOUNT_CONFLICT'):
            self.run_contract()

    def test_source_cell_helper_no_truthiness_currency(self):
        self.assertEqual(amount_cell(self.s[SHEETS[1]],2,12),10000)
        self.assertEqual(column_index('AI'),35)

if __name__=='__main__':
    unittest.main()
