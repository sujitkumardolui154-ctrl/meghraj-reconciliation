"""D-023 synthetic financial reference parity, no private ledgers or settlement."""
import copy
import importlib.util
from pathlib import Path
import unittest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "reference_financial_math", root / "reference_financial_math.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53


def invoice(headers=None, taxable="99.99", cgst="9.00",
            sgst="9.00", gross="117.99", number="MXP-SYNTH-001",
            marker_s=""):
    headers = list(headers if headers is not None else HEADERS_53)
    width = len(headers)
    i = {34: 10, 35: 11, 53: 13}[width]
    no_i = {34: 9, 35: 10, 53: 12}[width]
    pay_i = {34: 17, 35: 18, 53: 20}[width]
    values = [""] * width
    values[no_i] = number
    values[pay_i] = "100.00"
    values[i:i+4] = [taxable, cgst, sgst, gross]
    values[18] = marker_s
    return {
        "source_sheet": "Invoice Details.",
        "original_headers": headers,
        "original_values": values,
        "original_cell_types": ["s"] * width,
    }


def payment(credit="100.00"):
    cells = [""] * 12
    cells[8] = credit
    return cells


class D023FinancialMath(unittest.TestCase):
    def test_53_exact_gross_reference_only(self):
        row = invoice()
        original = copy.deepcopy(row)
        result = mod.invoice_reference_scenarios(row)
        self.assertEqual(result["status"], "REFERENCE_CALCULATION_ONLY")
        self.assertEqual(result["tds_reference_scenarios"]["1"]["tds_amount"], "1.00")
        self.assertEqual(result["tds_reference_scenarios"]["1"]["with_gst_reference_credit"], "116.99")
        self.assertEqual(result["tds_reference_scenarios"]["1"]["without_gst_reference_credit"], "98.99")
        self.assertFalse(result["approved_for_settlement"])
        self.assertEqual(original, row)

    def test_34_and_35_exact_header_positional_amounts(self):
        for headers in (HEADERS_34, HEADERS_35):
            with self.subTest(width=len(headers)):
                result = mod.invoice_reference_scenarios(invoice(headers=headers))
                self.assertEqual(result["status"], "REFERENCE_CALCULATION_ONLY")
                self.assertEqual(len(result["tds_reference_scenarios"]), 4)

    def test_half_up_taxable_base_not_gross(self):
        row = invoice(taxable="0.50", cgst="0.00", sgst="0.00", gross="0.50")
        r = mod.invoice_reference_scenarios(row)["tds_reference_scenarios"]
        self.assertEqual(r["1"]["tds_amount"], "0.01")
        self.assertEqual(r["3"]["tds_amount"], "0.02")
        self.assertEqual(r["3"]["with_gst_reference_credit"], "0.48")

    def test_mismatch_blocks_all_scenarios(self):
        result = mod.invoice_reference_scenarios(invoice(gross="117.98"))
        self.assertIn("INVOICE_GROSS_MISMATCH", result["flags"])
        self.assertEqual(result["tds_reference_scenarios"], {})

    def test_negative_nan_formula_precision_blank_block(self):
        for bad in ("-1", "NaN", "=10", "3.141", ""):
            with self.subTest(value=bad):
                result = mod.invoice_reference_scenarios(invoice(taxable=bad))
                self.assertIn("INVALID_TAXABLE", result["flags"])
                self.assertFalse(result["tds_reference_scenarios"])

    def test_wrong_header_cannot_be_inferred(self):
        row = invoice()
        row["original_headers"][13] = "WRONG"
        with self.assertRaises(mod.FinancialReferenceInputError):
            mod.invoice_reference_scenarios(row)

    def test_aggregate_no_match_or_financial_write(self):
        src = [invoice()]
        bank = [payment("116.99")]
        unchanged = copy.deepcopy([src, bank])
        result = mod.combined_reference_review(src, bank)
        self.assertEqual(result["amount_status_counts"]["REFERENCE_CALCULATION_ONLY"], 1)
        self.assertEqual(result["payment_allocation"], "NOT_EXECUTED")
        self.assertEqual(result["source_independent_parity"], "NOT_VERIFIED")
        self.assertFalse(result["approved_for_settlement"])
        self.assertFalse(result["financial_write_performed"])
        self.assertEqual([src, bank], unchanged)

    def test_aggregate_column_s_hold(self):
        result = mod.combined_reference_review([invoice(marker_s="PROTECTED")], [payment()])
        self.assertEqual(result["amount_status_counts"]["SOURCE_ELIGIBILITY_HOLD"], 1)

    def test_aggregate_duplicate_hold(self):
        result = mod.combined_reference_review([invoice(), invoice()], [payment()])
        self.assertEqual(result["amount_status_counts"]["SOURCE_ELIGIBILITY_HOLD"], 2)

    def test_aggregate_bad_gross_hold(self):
        result = mod.combined_reference_review([invoice(gross="117.98")], [payment()])
        self.assertEqual(result["amount_status_counts"]["SOURCE_AMOUNT_REVIEW_REQUIRED"], 1)

    def test_missing_payments_deny_composition(self):
        with self.assertRaises(Exception):
            mod.combined_reference_review([invoice()], [])

if __name__ == "__main__":
    unittest.main()
