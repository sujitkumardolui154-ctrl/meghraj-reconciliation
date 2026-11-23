"""Independent *fabricated* v2.18 writer regression, no real finance fixtures."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
import sys

from artifact_tool import Workbook, SpreadsheetFile, Blob

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v218_writer import OutputReviewBlocked, _read_snap, _protected, write_synthetic_v218_review

MANIFEST=json.loads((ROOT/'references'/'V218_OUTPUT_HEADER_LOCK_MANIFEST.json').read_text())


def source(path:Path):
    w=Workbook.create()
    for name in MANIFEST['sheets']:
        w.worksheets.add(name)
    pay=w.worksheets.get_item('PAYMNENT')
    inv=w.worksheets.get_item('Invoice Details.')
    pay.get_range('A1:L1').values=[[MANIFEST['headers']['PAYMNENT'][str(n)] for n in range(1,13)]]
    inv.get_range('A1:AH1').values=[[MANIFEST['headers']['Invoice Details.'][str(n)] for n in range(1,35)]]
    pay.get_range('F2').values=[['00001']]
    pay.get_range('G2').values=[['SYNTH-CLIENT-A']]
    pay.get_range('H2:I2').values=[[0,118]]
    pay.get_range('J2').formulas=[['=I2-H2']]
    pay.get_range('I3').values=[[17]]
    pay.get_range('F3').values=[['00001']]
    pay.get_range('G3').values=[['SYNTH-CLIENT-A']]
    inv.get_range('G2').values=[['00001']]
    inv.get_range('H2').values=[['SYNTH-CLIENT-A']]
    inv.get_range('J2').values=[['SYNTH-INV-1']]
    inv.get_range('K2:M2').values=[[100,9,9]]
    inv.get_range('N2').formulas=[['=K2+L2+M2']]
    inv.get_range('S3').values=[['SYNTH-ALREADY-PAID']]
    inv.get_range('G3').values=[['00002']]
    inv.get_range('J3').values=[['SYNTH-INV-PAID']]
    w.worksheets.get_item('Credit Note').get_range('A1').values=[['SYNTH-CN-NOT-EDITED']]
    w.worksheets.get_item('mail').get_range('B2').formulas=[['=3*4']]
    SpreadsheetFile.export_xlsx(w).save(str(path))


def models():
    return {2:['SUSPENSE','AWAITING INDEPENDENT SOURCE','SYNTH-INV-1',2,
               'REFERENCE REVIEW',0,'118.00','0.00','2026-11','00001','SYNTH-CLIENT-A'],
            3:['SUSPENSE','UNMATCHED; NOT POSTED',None,None,None,None,None,None,
               None,'00001','SYNTH-CLIENT-A']}

class TestFixedV218Writer(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.root=Path(self.d.name)
        self.src=self.root/'SYNTHETIC_SOURCE.xlsx'
        self.out=self.root/'SYNTHETIC_REVIEW.xlsx'
        source(self.src)
    def write(self,**kwargs):
        return write_synthetic_v218_review(self.src,self.out,
                    kwargs.pop('payment_models',models()),
                    kwargs.pop('invoice_models',{2:['00001','SYNTH-CLIENT-A',2,'118.00','REVIEW ONLY']}),**kwargs)
    def mutate(self,tab,cell,value,formula=False):
        wb=SpreadsheetFile.import_xlsx(Blob.load(str(self.src)))
        r=wb.worksheets.get_item(tab).get_range(cell)
        if formula:r.formulas=[[value]]
        else:r.values=[[value]]
        SpreadsheetFile.export_xlsx(wb).save(str(self.src))

    def test_review_output_preserves_all_original_source_cells_and_formulas(self):
        b=_read_snap(self.src)
        result=self.write()
        a=_read_snap(self.out)
        self.assertEqual(_protected(a),_protected(b))
        self.assertEqual(a[0],b[0])
        self.assertTrue(result['source_types_preserved'])
        self.assertFalse(result['financial_writes'])
        self.assertEqual(a[1]['PAYMNENT'][(2,10)][2],'I2-H2')
        self.assertEqual(a[1]['Invoice Details.'][(2,14)][2],'K2+L2+M2')

    def test_model_text_leading_zero_still_text(self):
        self.write()
        cells=_read_snap(self.out)[1]
        self.assertEqual(cells['PAYMNENT'][(2,22)],('text','00001',None))
        self.assertEqual(cells['Invoice Details.'][(2,35)],('text','00001',None))
        self.assertEqual(cells['PAYMNENT'][(2,6)],('text','00001',None))
        self.assertEqual(cells['Invoice Details.'][(2,7)],('text','00001',None))

    def test_empty_original_payment_l_preserved(self):
        self.write()
        self.assertNotIn((1,12),_read_snap(self.out)[1]['PAYMNENT'])

    def test_all_review_status_rows_covered(self):
        self.write()
        data=_read_snap(self.out)[1]['PAYMNENT']
        self.assertEqual([data[(i,13)][1] for i in (2,3)],['SUSPENSE','SUSPENSE'])

    def test_no_financial_ok_even_when_caller_requests_it(self):
        row=models();row[2][0]='OK'
        with self.assertRaisesRegex(OutputReviewBlocked,'REVIEW_ONLY_STATUS'):
            self.write(payment_models=row)
        self.assertFalse(self.out.exists())

    def test_no_real_source_names(self):
        with self.assertRaisesRegex(OutputReviewBlocked,'SYNTHETIC_FILENAME'):
            write_synthetic_v218_review(self.src,self.root/'REAL_OUTPUT.xlsx',models())

    def test_denies_unsafe_payment_note_formula(self):
        row=models();row[2][1]='=HYPERLINK("https://example.invalid")'
        with self.assertRaisesRegex(OutputReviewBlocked,'MODEL_FORMULA'):
            self.write(payment_models=row)

    def test_denies_unknown_payment_rows(self):
        row=models();row[4]=row[2]
        with self.assertRaisesRegex(OutputReviewBlocked,'MISSING_OR_EXTRA_PAYMENT_ROWS'):
            self.write(payment_models=row)

    def test_denies_missing_payment_rows(self):
        row=models();row.pop(3)
        with self.assertRaisesRegex(OutputReviewBlocked,'MISSING_OR_EXTRA_PAYMENT_ROWS'):
            self.write(payment_models=row)

    def test_denies_incorrect_model_shape(self):
        row=models();row[2].pop()
        with self.assertRaisesRegex(OutputReviewBlocked,'MODEL_ROW_SHAPE_INVALID'):
            self.write(payment_models=row)

    def test_denies_original_header_change(self):
        self.mutate('PAYMNENT','I1','Different Credit')
        with self.assertRaisesRegex(OutputReviewBlocked,'PROTECTED_HEADER_MISMATCH'):
            self.write()

    def test_denies_existing_model_cell(self):
        self.mutate('PAYMNENT','M2','old model')
        with self.assertRaisesRegex(OutputReviewBlocked,'EXISTING_MODEL_DATA_FORBIDDEN'):
            self.write()

    def test_denies_extra_sheet(self):
        w=SpreadsheetFile.import_xlsx(Blob.load(str(self.src)))
        w.worksheets.add('Injected')
        SpreadsheetFile.export_xlsx(w).save(str(self.src))
        with self.assertRaisesRegex(OutputReviewBlocked,'SOURCE_SHEET_ORDER_MISMATCH'):
            self.write()

    def test_denies_invoice_model_on_paid_marker_row(self):
        with self.assertRaisesRegex(OutputReviewBlocked,'PAID_MARKER_INVOICE_LINK'):
            self.write(invoice_models={3:['00002','SYNTH-CLIENT-A',3,'22.00','BAD']})

    def test_denies_original_source_overwrite(self):
        with self.assertRaisesRegex(OutputReviewBlocked,'SOURCE_OVERWRITE_FORBIDDEN'):
            write_synthetic_v218_review(self.src,self.src,models())

    def test_denies_existing_output_overwrite(self):
        self.out.write_bytes(b'ORIGINAL_ARTIFACT')
        with self.assertRaisesRegex(OutputReviewBlocked,'OUTPUT_OVERWRITE_FORBIDDEN'):
            self.write()
        self.assertEqual(self.out.read_bytes(),b'ORIGINAL_ARTIFACT')

    def test_denies_payment_model_numeric_sol(self):
        row=models();row[2][9]=1
        with self.assertRaisesRegex(OutputReviewBlocked,'TEXT_SOL_ID_REQUIRED'):
            self.write(payment_models=row)

    def test_unknown_invoice_model_row_denied(self):
        with self.assertRaisesRegex(OutputReviewBlocked,'UNKNOWN_INVOICE_MODEL_ROW'):
            self.write(invoice_models={9:['00001',None,None,None,None]})

    def test_false_positives_error_if_output_changes_protected_source(self):
        # Patched export deliberately tampers with a protected source value.
        from unittest.mock import patch
        original=SpreadsheetFile.export_xlsx
        def corrupt_export(wb):
            wb.worksheets.get_item('PAYMNENT').get_range('I2').values=[[999]]
            return original(wb)
        with patch.object(SpreadsheetFile,'export_xlsx',side_effect=corrupt_export):
            with self.assertRaisesRegex(OutputReviewBlocked,'PROTECTED_SOURCE_TYPE_VALUE_OR_FORMULA_CHANGED'):
                self.write()
        self.assertFalse(self.out.exists())

if __name__=='__main__':unittest.main()