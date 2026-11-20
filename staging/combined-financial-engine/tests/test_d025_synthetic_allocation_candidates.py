"""D-025 synthetic-only conservative invoice/payment candidate checks."""
import copy
from datetime import date, timedelta
import importlib.util
from pathlib import Path
import unittest

base = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "synthetic_allocation_candidates", base / "synthetic_allocation_candidates.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def inv(number="SYNTH-INV-A", sol="1505", *, months=None,
        date_string="2026-07-11", taxable="100.00",
        cgst="9.00", sgst="9.00", gross="118.00",
        protected=False, credit_note=False, sbisa=False):
    return {
        "source_kind": "SYNTHETIC", "invoice_no": number, "sol_id": sol,
        "invoice_date": date_string, "service_months": months or ["2026-05"],
        "taxable": taxable, "cgst": cgst, "sgst": sgst, "gross": gross,
        "protected": protected, "credit_note": credit_note, "sbisa": sbisa,
    }


def pay(number="SYNTH-PAY-A", sol="1505", *, ref="SYNTH-INV-A",
        months=None, date_string="2026-07-15", credit="117.00", sbisa=False):
    return {
        "source_kind": "SYNTHETIC", "payment_id": number, "sol_id": sol,
        "payment_date": date_string, "credit": credit, "invoice_ref": ref,
        "narration_months": [] if months is None else months, "sbisa": sbisa,
    }


def run(invoices=None, payments=None):
    return mod.suggest_synthetic_matches(
        [inv()] if invoices is None else invoices,
        [pay()] if payments is None else payments,
        synthetic_mode=True
    )


class D025SyntheticAllocatorTests(unittest.TestCase):
    def test_exact_same_sol_one_percent_candidate_review_only(self):
        invoice, payment = inv(), pay()
        before = copy.deepcopy([invoice, payment])
        result = run([invoice], [payment])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["tds_rate_reference"], 1)
        self.assertEqual(result["payment_allocation"], "NOT_EXECUTED")
        self.assertFalse(result["approved_for_settlement"])
        self.assertFalse(result["historical_data_processed"])
        self.assertEqual([invoice, payment], before)

    def test_all_four_tds_scenarios_are_reference_only(self):
        for rate, credit in ((0, "118.00"), (1, "117.00"), (2, "116.00"), (3, "115.00")):
            with self.subTest(rate=rate):
                result = run(payments=[pay(credit=credit)])
                self.assertEqual(result["candidate_count"], 1)
                self.assertEqual(result["candidates"][0]["tds_rate_reference"], rate)

    def test_half_up_rounded_one_percent(self):
        result = run(
            [inv(taxable="100.50", cgst="0.00", sgst="0.00", gross="100.50")],
            [pay(credit="99.49")])
        self.assertEqual(result["candidates"][0]["tds_rate_reference"], 1)

    def test_duplicate_payment_ids_hold_all(self):
        result = run(payments=[pay(), pay()])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["hold_count"], 2)
        self.assertTrue(all(x["reason"] == "DUPLICATE_PAYMENT_ID" for x in result["holds"]))

    def test_duplicate_invoice_key_holds(self):
        result = run(invoices=[inv(), inv()])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["holds"][0]["reason"], "DUPLICATE_INVOICE_REFERENCE")

    def test_multiple_same_sol_without_reference_held(self):
        result = run(
            [inv(), inv(number="SYNTH-INV-B")],
            [pay(ref=None)])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["holds"][0]["reason"], "MULTIPLE_SAME_SOL_INVOICES_REVIEW")

    def test_wrong_sol_blocks(self):
        result = run(payments=[pay(sol="1506")])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["holds"][0]["reason"], "CROSS_SOL_FORBIDDEN")

    def test_protected_invoice_and_credit_note_block(self):
        for key in ("protected", "credit_note"):
            with self.subTest(key=key):
                result = run(invoices=[inv(**{key: True})])
                self.assertEqual(result["candidate_count"], 0)
                self.assertEqual(result["holds"][0]["reason"],
                                 "PROTECTED_INVOICE" if key == "protected"
                                 else "CREDIT_NOTE_REVIEW")

    def test_180_day_boundary_and_future_block(self):
        for date_string, should_hold in (("2027-01-08", True),
                                         ("2026-07-01", True),
                                         ("2026-07-15", False)):
            with self.subTest(date=date_string):
                result = run(payments=[pay(date_string=date_string)])
                self.assertEqual(result["candidate_count"] == 0, should_hold)

    def test_month_contradiction_and_multi_month_match(self):
        invoice = inv(months=["2026-03", "2026-04", "2026-05"])
        yes = run([invoice], [pay(months=["2026-03", "2026-04", "2026-05"])])
        self.assertEqual(yes["candidate_count"], 1)
        no = run([invoice], [pay(months=["2026-04", "2026-05"])])
        self.assertEqual(no["holds"][0]["reason"], "CONTRADICTORY_SERVICE_PERIOD")

    def test_partial_payment_without_approved_allocations_held(self):
        result = run(payments=[pay(credit="50.00")])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["holds"][0]["reason"], "PARTIAL_PAYMENT_REVIEW_REQUIRED")

    def test_multiple_bank_credits_to_same_invoice_held(self):
        result = run(payments=[pay(), pay(number="SYNTH-PAY-B")])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["hold_count"], 2)
        self.assertTrue(all(x["reason"] == "MULTI_PAYMENT_INVOICE_REVIEW" for x in result["holds"]))

    def test_sbisa_sol_1_works_only_when_both_eligible(self):
        invoice = inv(sol="", sbisa=True)
        result = run([invoice], [pay(sol="1", sbisa=True)])
        self.assertEqual(result["candidate_count"], 1)
        blocked = run([invoice], [pay(sol="1", sbisa=False)])
        self.assertEqual(blocked["candidate_count"], 0)
        self.assertEqual(blocked["holds"][0]["reason"], "SBISA_IDENTITY_CONFLICT")

    def test_no_real_payment_or_invoice_can_enter(self):
        invoice = inv()
        payment = pay()
        for field, value, target in (
            ("source_kind", "REAL", "invoice"),
            ("invoice_no", "MXP21569", "invoice"),
            ("source_kind", "REAL", "payment"),
            ("payment_id", "BANK-123", "payment"),
        ):
            with self.subTest(field=field, target=target):
                a, b = copy.deepcopy(invoice), copy.deepcopy(payment)
                (a if target == "invoice" else b)[field] = value
                with self.assertRaises(mod.SyntheticAllocationBlocked):
                    run([a], [b])

    def test_mode_cannot_be_guessed(self):
        with self.assertRaises(mod.SyntheticAllocationBlocked):
            mod.suggest_synthetic_matches([inv()], [pay()])
        with self.assertRaises(mod.SyntheticAllocationBlocked):
            mod.suggest_synthetic_matches([inv()], [pay()], synthetic_mode="True")

    def test_bad_gross_formula_and_invalid_date_are_denied(self):
        for field, value in (("gross", "117.99"), ("taxable", "=100"),
                             ("invoice_date", "2026-02-30"),
                             ("service_months", ["May 2026"])):
            with self.subTest(field=field):
                row = inv()
                row[field] = value
                with self.assertRaises(mod.SyntheticAllocationBlocked):
                    run([row], [pay()])

    def test_ambiguous_tds_rate_held(self):
        result = run([inv(taxable="0.01", cgst="0.00", sgst="0.00", gross="0.01")],
                     [pay(credit="0.01")])
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["holds"][0]["reason"], "AMBIGUOUS_TDS_RATE")


if __name__ == "__main__":
    unittest.main()
