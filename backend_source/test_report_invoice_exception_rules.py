"""Synthetic owner-approved invoice exception tests: no financial I/O."""
import unittest

from report_invoice_exception_rules import (
    CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES,
    FORCED_ERROR_INVOICES,
    invoice_report_error_reason,
    route_payment_report,
)


class OwnerInvoiceExceptionRoutingTest(unittest.TestCase):
    def test_explicit_count_error(self):
        for kind in ("ok", "unpaid", "error-value"):
            with self.subTest(kind=kind):
                self.assertEqual(
                    route_payment_report(
                        {"invoice_no": "MXP/2025-2026-04"}, kind
                    ),
                    ("error-value", "OWNER_FLAGGED_INVOICE_COUNT_ERROR"),
                )

    def test_four_conditional_invoices_need_verified_multiple_allocations(self):
        self.assertEqual(len(CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES), 4)
        for invoice in CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES:
            with self.subTest(invoice=invoice):
                row = {"invoice_no": invoice,
                       "verified_allocation_count": 2,
                       "allocation_verification": "VERIFIED"}
                self.assertEqual(route_payment_report(row, "ok"),
                                 ("error-value", "VERIFIED_MULTIPLE_ALLOCATION"))
                row["verified_allocation_count"] = 1
                self.assertEqual(route_payment_report(row, "ok"), ("ok", None))
                row["verified_allocation_count"] = 2
                row["allocation_verification"] = "PENDING"
                self.assertEqual(route_payment_report(row, "ok"), ("ok", None))

    def test_duplicate_invoice_count_is_not_allocation_evidence(self):
        for invoice in CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES:
            row = {"invoice_no": invoice, "duplicate_invoice_rows": 2}
            self.assertEqual(route_payment_report(row, "unpaid"),
                             ("unpaid", None))

    def test_reject_unverified_or_invalid_allocation_counts(self):
        for count in (True, "2", 1.5, None, -2, 0):
            with self.subTest(count=count):
                row = {"invoice_no": "MXP10092",
                       "verified_allocation_count": count,
                       "allocation_verification": "VERIFIED"}
                self.assertIsNone(invoice_report_error_reason(row))

    def test_other_invoices_and_previous_errors_unchanged(self):
        self.assertEqual(
            route_payment_report({"invoice_no": "MXP12345"}, "error-value"),
            ("error-value", None),
        )
        self.assertEqual(
            route_payment_report({"invoice_no": "MXP12345",
                                  "verified_allocation_count": 4,
                                  "allocation_verification": "VERIFIED"}, "ok"),
            ("error-value", "VERIFIED_MULTIPLE_ALLOCATION"),
        )

    def test_any_invoice_multistage_verified_routes_to_error(self):
        for invoice in ("MXP12345", "MXP9014", "MXP/2026-2027-77"):
            row = {
                "invoice_no": invoice,
                "verified_reconciliation_stage_count": 2,
                "reconciliation_stage_verification": "VERIFIED",
            }
            self.assertEqual(
                route_payment_report(row, "ok"),
                ("error-value", "VERIFIED_MULTISTAGE_RECONCILIATION"),
            )
            row["reconciliation_stage_verification"] = "PENDING"
            self.assertEqual(route_payment_report(row, "ok"), ("ok", None))
            row["reconciliation_stage_verification"] = "VERIFIED"
            row["verified_reconciliation_stage_count"] = 1
            self.assertEqual(route_payment_report(row, "ok"), ("ok", None))

    def test_any_invoice_verified_conflict_routes_to_error(self):
        row = {"invoice_no": "MXP76543",
               "conflict_verification": "VERIFIED",
               "reconciliation_conflict": True}
        self.assertEqual(
            route_payment_report(row, "unpaid"),
            ("error-value", "VERIFIED_RECONCILIATION_CONFLICT"),
        )
        row["reconciliation_conflict"] = False
        self.assertEqual(route_payment_report(row, "unpaid"), ("unpaid", None))
        row["reconciliation_conflict"] = True
        row["conflict_verification"] = "UNKNOWN"
        self.assertEqual(route_payment_report(row, "unpaid"), ("unpaid", None))

    def test_unsupported_multistage_evidence_is_not_accepted(self):
        for count in (True, "2", -1, 0, 1.5):
            row = {
                "invoice_no": "MXP6789",
                "reconciliation_stage_verification": "VERIFIED",
                "verified_reconciliation_stage_count": count,
            }
            self.assertEqual(route_payment_report(row, "ok"), ("ok", None))

    def test_fail_closed_on_missing_invoice(self):
        with self.assertRaises(ValueError):
            invoice_report_error_reason({})
        with self.assertRaises(ValueError):
            route_payment_report({"invoice_no": "MXP10092"}, "suspense")

    def test_source_row_not_modified(self):
        row = {"invoice_no": "MXP/2025-2026-04",
               "original_values": ["source", "values"]}
        snapshot = dict(row)
        route_payment_report(row, "ok")
        self.assertEqual(row, snapshot)

    def test_exact_owner_invoice_rules(self):
        self.assertEqual(FORCED_ERROR_INVOICES, {"MXP/2025-2026-04"})
        self.assertEqual(CONDITIONAL_MULTIPLE_ALLOCATION_INVOICES,
                         {"MXP10092", "MXP10565", "MXP10566", "MXP9014"})


if __name__ == "__main__":
    unittest.main()
