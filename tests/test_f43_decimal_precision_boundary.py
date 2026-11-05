"""Synthetic exact arithmetic tests; no live database access."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard_source"))
from dil_query_contract import QueryDenied, decimal_total


class DecimalPrecisionBoundaryTests(unittest.TestCase):
    def test_twenty_maximum_precision_amounts(self):
        amount = "999999999999999999.999999999999"
        self.assertEqual(decimal_total([amount] * 20),
                         "19999999999999999999.999999999980")

    def test_cancellation_preserves_fraction(self):
        self.assertEqual(decimal_total([
            "999999999999999999.999999999999",
            "-999999999999999999.999999999998",
        ]), "0.000000000001")

    def test_overlong_and_exponent_denied(self):
        for value in ("1e1000", "1." + "0" * 13, "9" * 19):
            with self.subTest(value=value):
                with self.assertRaises(QueryDenied):
                    decimal_total([value])


if __name__ == "__main__":
    unittest.main()
