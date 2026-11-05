"""Synthetic positional regression: no live database or financial writes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53, export_values_53


class HeaderProjectionTests(unittest.TestCase):
    def test_35_preserves_both_branch_codes_and_financial_fields(self):
        values = [f"source-{i}" for i in range(35)]
        row = {"original_values": values, "original_headers": HEADERS_35}
        projected = export_values_53(row)
        self.assertEqual(len(projected), 53)
        self.assertEqual(projected[:8], values[:8])
        self.assertEqual(projected[10], values[8])
        self.assertEqual(projected[11:37], values[9:])
        self.assertEqual(projected[12], values[10])  # Invoice No
        self.assertEqual(projected[20], values[18])  # Payment Received
        self.assertEqual(projected[27], values[25])  # Outstanding
        self.assertTrue(all(projected[i] == "" for i in [8, 9, *range(37, 53)]))
        self.assertEqual(values, [f"source-{i}" for i in range(35)])

    def test_34_and_53_remain_compatible(self):
        for headers in (HEADERS_34, HEADERS_53):
            values = [f"source-{i}" for i in range(len(headers))]
            projected = export_values_53(
                {"original_values": values, "original_headers": headers}
            )
            self.assertEqual(len(projected), 53)
            if len(headers) == 34:
                self.assertEqual(projected[:8], values[:8])
                self.assertEqual(projected[11:37], values[8:])
                self.assertEqual(projected[10], "")
            else:
                self.assertEqual(projected, values)

    def test_bad_35_header_order_rejected(self):
        headers = list(HEADERS_35)
        headers[8], headers[9] = headers[9], headers[8]
        with self.assertRaises(ValueError):
            export_values_53({"original_values": ["x"] * 35, "original_headers": headers})


if __name__ == "__main__":
    unittest.main()
