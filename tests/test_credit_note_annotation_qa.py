"""Offline synthetic regression: approved annotated Credit Note recognition.

No finance/network calls and no source mutation.
"""
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend_source"))
from credit_note_53_adapter import (
    CREDIT_NOTE_TOKEN, REPORT_HEADERS, header_mapping, project_credit_notes,
)
from invoice_source_schema import HEADERS_35, HEADERS_53


def invoice(width, status, ref="MXP12345"):
    if width == 35:
        a=[""]*35
        a[6]="000123"
        a[7]="SOURCE CLIENT"
        a[8]="DIFFERENT ALTERNATE CODE"
        a[10]=ref
        a[11]="100";a[12]="9";a[13]="9";a[14]="118"
        a[18]=status
        return a
    a=[""]*53
    a[6]="000123";a[7]="SOURCE CLIENT"
    a[10]="DIFFERENT ALTERNATE CODE"
    a[12]=ref;a[13]="100";a[14]="9";a[15]="9";a[16]="118"
    a[20]=status
    return a


class CreditNoteAnnotationTests(unittest.TestCase):
    def _project(self, status, width=35):
        header=HEADERS_35 if width == 35 else HEADERS_53
        row=invoice(width,status)
        original=list(row)
        actual, stats = project_credit_notes(header,[row])
        self.assertEqual(row,original)
        self.assertEqual(len(actual),1)
        self.assertEqual(len(actual[0]),18)
        self.assertEqual(actual[0]["Invoice No"],"MXP12345")
        self.assertEqual(actual[0]["Branch Code"],"000123")
        self.assertEqual(actual[0]["Client Name"],"SOURCE CLIENT")
        return actual[0],stats

    def test_01_exact_credit_note_35(self):
        result,stats=self._project("CREDIT NOTE")
        self.assertEqual(result["Credi note"],"CREDIT NOTE")
        self.assertEqual(stats["credit_note_invoices"],1)

    def test_02_annotated_april_2026_35(self):
        result,stats=self._project("Credit Note @April 2026")
        self.assertEqual(result["Credi note"],"CREDIT NOTE")

    def test_03_annotated_historical_issue_date(self):
        result,_=self._project("CREDIT NOTE @ 30/11/2024")
        self.assertEqual(result["Credi note"],"CREDIT NOTE")

    def test_04_annotated_historical_extra_spacing(self):
        result,_=self._project(" Credit   Note   @ 30 12 2024 ")
        self.assertEqual(result["Credi note"],"CREDIT NOTE")

    def test_05_credit_norte_approved_typo(self):
        result,_=self._project("CREDIT NORTE")
        self.assertEqual(result["Credi note"],"CREDIT NOTE")

    def test_06_not_credit_notebook(self):
        result,_=self._project("CREDIT NOTEBOOK")
        self.assertEqual(result["Credi note"],"")

    def test_07_not_credit_note_prefix_suffix(self):
        result,_=self._project("NOTCREDIT NOTEPLUS")
        self.assertEqual(result["Credi note"],"")

    def test_08_unapproved_credite_variant_does_not_autofix(self):
        result,_=self._project("CREDITE NOTE")
        self.assertEqual(result["Credi note"],"")

    def test_09_numeric_paid_marker_no_note(self):
        result,_=self._project("100.50")
        self.assertEqual(result["Credi note"],"")

    def test_10_source_53_annotated(self):
        result,_=self._project("Credit Note @April 2026",53)
        self.assertEqual(result["Credi note"],"CREDIT NOTE")

    def test_11_source_53_no_note(self):
        result,_=self._project("Paid via transfer",53)
        self.assertEqual(result["Credi note"],"")

    def test_12_exact_35_header_lock(self):
        a=list(HEADERS_35);a[6],a[8]=a[8],a[6] # equal duplicate, does not change positions
        # Now change a financial positional header in an observable way
        a[14]="Changed Gross Label"
        with self.assertRaises(ValueError):
            project_credit_notes(a,[invoice(35,"CREDIT NOTE")])

    def test_13_53_row_length_guard(self):
        with self.assertRaises(ValueError):
            project_credit_notes(HEADERS_53,[invoice(53,"CREDIT NOTE")[:-1]])

    def test_14_no_confusion_between_35_duplicate_code_and_real_code(self):
        result,_=self._project("CREDIT NOTE")
        self.assertEqual(result["Branch Code"],"000123")

    def test_15_mixed_labels_across_source_rows(self):
        rows=[invoice(35,x,ref=f"MXP12{i:03}") for i,x in enumerate(["CREDIT NOTE","CREDIT NOTEBOOK","Credit Note @April 2026"])]
        result,stats=project_credit_notes(HEADERS_35,rows)
        self.assertEqual([r["Credi note"] for r in result],["CREDIT NOTE","","CREDIT NOTE"])
        self.assertEqual(stats["credit_note_invoices"],2)

    def test_16_no_financial_mutation(self):
        a=invoice(35,"CREDIT NOTE @April 2026")
        old=list(a)
        self._project("CREDIT NOTE @April 2026")
        self.assertEqual(a,old)

    def test_17_regex_independent_phrase_boundaries(self):
        self.assertIsNone(CREDIT_NOTE_TOKEN.search("CREDIT NOTEBOOK"))
        self.assertIsNotNone(CREDIT_NOTE_TOKEN.search("PAID CREDIT NOTE @ 12/10/2026"))

    def test_18_preserve_approved_18_column_header_typo(self):
        self.assertEqual(len(REPORT_HEADERS),18)
        self.assertEqual(REPORT_HEADERS[-1],"Credi note")


if __name__=="__main__":
    unittest.main()
