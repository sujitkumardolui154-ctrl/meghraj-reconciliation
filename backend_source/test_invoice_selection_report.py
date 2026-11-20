"""Offline synthetic QA: no Firestore, no finance writes."""
import unittest
from invoice_selection_report import select_verified_invoices


def fixture(number, kind="unpaid", balance=True):
    columns = [""] * 53
    columns[12] = number
    columns[20] = "0" if kind == "unpaid" else "118"
    return {
        "invoice_no": number,
        "export_values": columns,
        "payment_report": kind,
        "balance_valid": balance,
        "source_sheet": "SYNTHETIC",
        "source_row": 2,
    }


class InvoiceSelectionReportTests(unittest.TestCase):
    def test_random_order_and_full_53_columns(self):
        records = [fixture("MXP1001", "ok"), fixture("MXP1003", balance=False)]
        result = select_verified_invoices(
            ["MXP1003", "MXP1002", "MXP1001"], records
        )
        self.assertEqual([v["invoice_no"] for v in result["matches"]],
                         ["MXP1003", "MXP1001"])
        self.assertEqual([v["reason"] for v in result["review"]],
                         ["NOT_FOUND_IN_VERIFIED_REPORT_SOURCE"])
        self.assertEqual(len(result["matches"][0]["values"]), 53)
        self.assertTrue(result["matches"][0]["balance_review"])
        self.assertEqual(result["requested_count"], 3)

    def test_duplicate_database_record_is_not_arbitrarily_chosen(self):
        result = select_verified_invoices(
            ["MXP1001"], [fixture("MXP1001"), fixture("MXP1001")]
        )
        self.assertEqual(result["matched_count"], 0)
        self.assertEqual(result["review"][0]["reason"],
                         "DUPLICATE_DATABASE_INVOICE_MATCH")

    def test_mismatched_source_invoice_is_rejected(self):
        row = fixture("MXP1001")
        row["export_values"][12] = "MXP9999"
        result = select_verified_invoices(["MXP1001"], [row])
        self.assertEqual(result["review"][0]["reason"], "DATABASE_SOURCE_CONFLICT")

    def test_duplicate_requested_invoice_is_rejected(self):
        with self.assertRaises(ValueError):
            select_verified_invoices(["MXP1001", "MXP1001"], [])

    def test_nothing_fabricated_when_all_missing(self):
        result = select_verified_invoices(["MXP9999"], [])
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["review_count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
