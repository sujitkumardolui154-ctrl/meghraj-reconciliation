"""D-026 synthetic-only full/partial/split simulations with immutable sources."""
import copy
import importlib.util
from pathlib import Path
import unittest

base = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "synthetic_waterfall", base / "synthetic_waterfall.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def inv(number="SYNTH-INV-A", sol="1505", *, priority=1,
        taxable="100.00", cgst="9.00", sgst="9.00", gross="118.00",
        rate=1, date="2026-07-11", months=None,
        protected=False, credit_note=False, sbisa=False):
    return {
        "source_kind": "SYNTHETIC", "invoice_no": number,
        "sol_id": sol, "approved_tds_rate": rate,
        "simulation_priority": priority,
        "invoice_date": date,
        "service_months": ["2026-05"] if months is None else months,
        "taxable": taxable, "cgst": cgst, "sgst": sgst,
        "gross": gross, "protected": protected,
        "credit_note": credit_note, "sbisa": sbisa,
    }


def pay(number="SYNTH-PAY-A", sol="1505", *, ref="SYNTH-INV-A",
        credit="117.00", date="2026-07-15", months=None,
        fifo=False, sbisa=False):
    return {
        "source_kind": "SYNTHETIC", "payment_id": number,
        "sol_id": sol, "payment_date": date,
        "credit": credit, "invoice_ref": ref,
        "narration_months": [] if months is None else months,
        "allow_synthetic_fifo": fifo, "sbisa": sbisa,
    }


def run(invoices=None, payments=None):
    return mod.simulate_synthetic_waterfall(
        [inv()] if invoices is None else invoices,
        [pay()] if payments is None else payments,
        synthetic_mode=True
    )


class D026SyntheticWaterfallTests(unittest.TestCase):
    def test_complete_match_never_settles(self):
        src, bank = inv(), pay()
        original = copy.deepcopy([src, bank])
        result = run([src], [bank])
        self.assertEqual(result["assignment_count"], 1)
        self.assertEqual(result["simulated_assignments"][0]["status"], "SIMULATED_FULL")
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-A"], "0.00")
        self.assertEqual(result["payment_allocation"], "SIMULATED_ONLY_NOT_EXECUTED")
        self.assertFalse(result["approved_for_settlement"])
        self.assertFalse(result["financial_write_performed"])
        self.assertFalse(result["historical_records_processed"])
        self.assertEqual([src, bank], original)

    def test_partial_then_full_two_payments(self):
        result = run(payments=[
            pay(credit="50.00", date="2026-07-15"),
            pay(number="SYNTH-PAY-B", credit="67.00", date="2026-07-16"),
        ])
        self.assertEqual(result["assignment_count"], 2)
        self.assertEqual([x["status"] for x in result["simulated_assignments"]],
                         ["SIMULATED_PARTIAL", "SIMULATED_FULL"])
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-A"], "0.00")

    def test_explicit_split_across_two_invoices(self):
        invoices = [
            inv(),
            inv(number="SYNTH-INV-B", priority=2, date="2026-07-12",
                taxable="50.00", cgst="4.50", sgst="4.50",
                gross="59.00", rate=1),
        ]
        payment = pay(ref=None, credit="175.50",
                      months=["2026-05"], fifo=True)
        result = run(invoices, [payment])
        self.assertEqual(result["assignment_count"], 2)
        self.assertEqual(result["hold_count"], 0)
        self.assertEqual(
            [x["synthetic_credit"] for x in result["simulated_assignments"]],
            ["117.00", "58.50"])
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-B"], "0.00")
        self.assertEqual(result["invoice_priority"], "EXPLICIT_SYNTHETIC_ORDER_ONLY")

    def test_unreferenced_payment_needs_fifo_opt_in(self):
        result = run(payments=[pay(ref=None, fifo=False)])
        self.assertEqual(result["hold_count"], 1)
        self.assertEqual(result["holds"][0]["reason"], "UNREFERENCED_PAYMENT_NEEDS_REVIEW")

    def test_two_invoice_ambiguity_without_fifo(self):
        result = run([inv(), inv(number="SYNTH-INV-B", priority=2)],
                     [pay(ref=None, months=["2026-05"])])
        self.assertEqual(result["holds"][0]["reason"], "MULTIPLE_SAME_SOL_INVOICES_REVIEW")
        self.assertEqual(result["assignment_count"], 0)

    def test_multisplit_without_period_held(self):
        result = run([inv(), inv(number="SYNTH-INV-B", priority=2)],
                     [pay(ref=None, fifo=True, credit="150.00")])
        self.assertEqual(result["holds"][0]["reason"],
                         "MULTI_INVOICE_REQUIRES_PERIOD_EVIDENCE")

    def test_tied_priority_holds(self):
        result = run([inv(), inv(number="SYNTH-INV-B", priority=1)],
                     [pay(ref=None, fifo=True, months=["2026-05"])])
        self.assertEqual(result["holds"][0]["reason"], "AMBIGUOUS_SYNTHETIC_PRIORITY")
        self.assertEqual(result["assignment_count"], 0)

    def test_overpayment_atomic_no_partial_application(self):
        result = run(payments=[
            pay(credit="50.00"),
            pay(number="SYNTH-PAY-B", credit="70.00", date="2026-07-16"),
        ])
        self.assertEqual(result["assignment_count"], 1)
        self.assertEqual(result["holds"][0]["reason"],
                         "OVERPAYMENT_OR_UNALLOCATABLE_REMAINDER")
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-A"], "67.00")

    def test_multi_invoice_overflow_holds_whole_payment(self):
        result = run([inv(), inv(number="SYNTH-INV-B", priority=2)],
                     [pay(ref=None, credit="235.00", fifo=True, months=["2026-05"])])
        self.assertEqual(result["assignment_count"], 0)
        self.assertEqual(result["hold_count"], 1)
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-A"], "117.00")

    def test_duplicate_payment_ids_all_held(self):
        result = run(payments=[pay(), pay()])
        self.assertEqual(result["hold_count"], 2)
        self.assertEqual(result["assignment_count"], 0)
        self.assertTrue(all(x["reason"] == "DUPLICATE_PAYMENT_ID"
                            for x in result["holds"]))

    def test_duplicate_invoice_reference_held(self):
        result = run([inv(), inv()], [pay()])
        self.assertEqual(result["holds"][0]["reason"], "DUPLICATE_INVOICE_REFERENCE")
        self.assertEqual(result["assignment_count"], 0)

    def test_credit_note_and_protected_block(self):
        for field, expected in (("protected", "PROTECTED_INVOICE"),
                                ("credit_note", "CREDIT_NOTE_REVIEW")):
            with self.subTest(field=field):
                result = run([inv(**{field: True})], [pay()])
                self.assertEqual(result["assignment_count"], 0)
                self.assertEqual(result["holds"][0]["reason"], expected)

    def test_cross_sol_and_sbisa_marker_protected(self):
        result = run(payments=[pay(sol="1506")])
        self.assertEqual(result["holds"][0]["reason"], "CROSS_SOL_FORBIDDEN")
        yes = run([inv(sol="", sbisa=True)],
                  [pay(sol="1", sbisa=True)])
        self.assertEqual(yes["assignment_count"], 1)
        no = run([inv(sol="", sbisa=True)],
                 [pay(sol="1", sbisa=False)])
        self.assertEqual(no["holds"][0]["reason"], "SBISA_IDENTITY_CONFLICT")

    def test_date_window_and_service_contradiction(self):
        out = run(payments=[pay(date="2027-01-08")])
        self.assertEqual(out["holds"][0]["reason"], "PAYMENT_OUTSIDE_180_DAYS")
        contradiction = run(
            [inv(months=["2026-03", "2026-04", "2026-05"])],
            [pay(months=["2026-04", "2026-05"])])
        self.assertEqual(contradiction["holds"][0]["reason"], "CONTRADICTORY_SERVICE_PERIOD")

    def test_half_up_net_receivable(self):
        result = run(
            [inv(taxable="0.50", cgst="0.00", sgst="0.00",
                 gross="0.50", rate=1)],
            [pay(credit="0.49")])
        self.assertEqual(result["assignment_count"], 1)
        self.assertEqual(result["simulated_remaining_net"]["SYNTH-INV-A"], "0.00")

    def test_explicit_rate_is_mandatory_and_no_rate_guessing(self):
        for invalid in (None, True, "1", -1, 4):
            with self.subTest(invalid=invalid):
                with self.assertRaises(mod.SyntheticAllocationBlocked):
                    run([inv(rate=invalid)], [pay()])

    def test_real_sources_rejected_even_with_opt_in(self):
        for target, value in (("invoice_no", "MXP12345"),
                              ("source_kind", "HISTORICAL")):
            with self.subTest(target=target):
                row = inv()
                row[target] = value
                with self.assertRaises(mod.SyntheticAllocationBlocked):
                    run([row], [pay()])
        with self.assertRaises(mod.SyntheticAllocationBlocked):
            mod.simulate_synthetic_waterfall([inv()], [pay()], synthetic_mode=False)

    def test_bad_order_type_denied(self):
        for invalid in (0, -1, True, "1", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(mod.SyntheticAllocationBlocked):
                    run([inv(priority=invalid)], [pay()])

    def test_deterministic_repeat_no_mutations(self):
        ins = [inv()]
        pays = [pay(credit="60.00"), pay(number="SYNTH-PAY-B",
                                        credit="57.00", date="2026-07-16")]
        original = copy.deepcopy([ins, pays])
        first = run(ins, pays)
        second = run(ins, pays)
        self.assertEqual(first, second)
        self.assertEqual([ins, pays], original)


if __name__ == "__main__":
    unittest.main()
