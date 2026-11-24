"""R17 independent synthetic-only contract QA; no Firebase, Excel writer, or DB."""
from dataclasses import replace
from datetime import date
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))

from sbi_r17_synthetic_financial_shadow import (
    SyntheticInvoice, SyntheticPayment, SyntheticReservation,
    SyntheticOnlyRefusal, money, exact_tds_hypotheses,
    review_one_payment_invoice, dnm01_review, audit_shadow_reservations,
)


def inv(**overrides):
    source = SyntheticInvoice(
        key="SYN-MXP-001", sol="9001", client="SYNTHETIC ALPHA",
        taxable="1000.00", gross="1180.00", gst="180.00",
        outstanding="1180.00", issued_at=date(2026, 9, 1),
        service_periods=("2026-09",), original_s_marker=None,
    )
    return replace(source, **overrides)


def pay(**overrides):
    source = SyntheticPayment(
        key="SYN-PAY-001", sol="9001", client="SYNTHETIC ALPHA",
        credit="1160.00", booked_at=date(2026, 9, 15),
        narration_refs=("SYN-MXP-001",),
        service_periods=("2026-09",),
        gst_component_only=False, original_bank_status="",
    )
    return replace(source, **overrides)


def edge(amount="100.00", payment="SYN-PAY-001", invoice="SYN-MXP-001"):
    return SyntheticReservation(payment_key=payment, invoice_key=invoice, amount=amount)


class R17SyntheticTDSAndEvidenceTests(unittest.TestCase):
    def test_01_exact_tds_two_percent_is_only_hypothesis(self):
        out = review_one_payment_invoice(pay(), inv())
        self.assertEqual(out["tds_rate_hypotheses_not_approved"], [2])
        self.assertEqual(out["decision"], "CANDIDATE_FOR_INDEPENDENT_REVIEW")
        self.assertIsNone(out["financial_status"])
        self.assertFalse(out["payment_allocated"])

    def test_02_0_1_2_3_percent_rates_decimal(self):
        for rate, credit in ((0, "1180.00"), (1, "1170.00"),
                             (2, "1160.00"), (3, "1150.00")):
            with self.subTest(rate=rate):
                self.assertEqual(exact_tds_hypotheses(pay(credit=credit), inv()), (rate,))

    def test_03_half_up_3_percent_105_50_is_3_17(self):
        i = inv(taxable="105.50", gross="118.00", gst="12.50", outstanding="118.00")
        self.assertEqual(exact_tds_hypotheses(pay(credit="114.83"), i), (3,))

    def test_04_zero_taxable_competing_rates_is_held(self):
        i = inv(taxable="0.00", gross="100.00", gst="0.00", outstanding="100.00")
        out = review_one_payment_invoice(pay(credit="100.00"), i)
        self.assertEqual(out["tds_rate_hypotheses_not_approved"], [0,1,2,3])
        self.assertIn("COMPETING_TDS_RATE_HYPOTHESES", out["blocker_codes"])

    def test_05_monetary_float_is_rejected(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "MONEY_TYPE_UNSAFE"):
            money(1.005)

    def test_06_nan_and_infinity_are_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(SyntheticOnlyRefusal, "MONEY_NOT_FINITE"):
                    money(value)

    def test_07_subcent_payment_is_rejected_not_silently_rounded(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "MONEY_MORE_THAN_TWO_DECIMALS"):
            review_one_payment_invoice(pay(credit="1160.005"), inv())

    def test_08_negative_payment_never_inherits_OK(self):
        out = review_one_payment_invoice(pay(credit="-5.00", original_bank_status="OK"), inv())
        self.assertIn("NONPOSITIVE_BANK_CREDIT", out["blocker_codes"])
        self.assertIn("BANK_SOURCE_STATUS_REQUIRES_INDEPENDENT_VERIFICATION",
                      out["blocker_codes"])
        self.assertIsNone(out["financial_status"])

    def test_09_numeric_zero_invoice_S_is_protected(self):
        out = review_one_payment_invoice(pay(), inv(original_s_marker=0))
        self.assertIn("INVOICE_S_NONBLANK_PROTECTED", out["blocker_codes"])

    def test_10_source_S_string_zero_is_protected(self):
        out = review_one_payment_invoice(pay(), inv(original_s_marker="0"))
        self.assertIn("INVOICE_S_NONBLANK_PROTECTED", out["blocker_codes"])

    def test_11_exact_text_SOL_no_left_padding_coercion(self):
        out = review_one_payment_invoice(pay(sol="09001"), inv())
        self.assertIn("UNAPPROVED_CROSS_SOL", out["blocker_codes"])

    def test_12_unverified_cross_SOL_is_held(self):
        out = review_one_payment_invoice(pay(sol="9002"), inv())
        self.assertIn("UNAPPROVED_CROSS_SOL", out["blocker_codes"])

    def test_13_SBISA_collecting_SOL_one_never_autopasses(self):
        out = review_one_payment_invoice(pay(sol="1"), inv(sol=""))
        self.assertIn("SBISA_BLANK_SOL_DOCUMENTARY_REVIEW", out["blocker_codes"])
        self.assertFalse(out["payment_allocated"])

    def test_14_SBISA_cross_SOL_must_be_reviewed(self):
        out = review_one_payment_invoice(pay(sol="1"), inv(sol="9001"))
        self.assertIn("SBISA_COLLECTING_SOL_REVIEW", out["blocker_codes"])

    def test_15_GST_component_needs_ledger_evidence(self):
        out = review_one_payment_invoice(pay(credit="180.00", gst_component_only=True), inv())
        self.assertIn("GST_COMPONENT_REQUIRES_SEPARATE_LEDGER_PROOF", out["blocker_codes"])

    def test_16_contradictory_MXP_reference_blocks(self):
        out = review_one_payment_invoice(pay(narration_refs=("SYN-MXP-002",)), inv())
        self.assertIn("CONTRADICTORY_OR_MULTIPLE_MXP_REFERENCES", out["blocker_codes"])

    def test_17_multiple_MXP_references_hold_for_review(self):
        out = review_one_payment_invoice(
            pay(narration_refs=("SYN-MXP-001", "SYN-MXP-002")), inv()
        )
        self.assertIn("CONTRADICTORY_OR_MULTIPLE_MXP_REFERENCES", out["blocker_codes"])

    def test_18_reference_missing_never_auto_allocation(self):
        out = review_one_payment_invoice(pay(narration_refs=()), inv())
        self.assertIn("EXACT_MXP_REFERENCE_NOT_PROVEN", out["blocker_codes"])

    def test_19_explicit_service_period_conflict_hold(self):
        out = review_one_payment_invoice(pay(service_periods=("2026-08",)), inv())
        self.assertIn("SERVICE_PERIOD_CONFLICT", out["blocker_codes"])

    def test_20_multi_month_incomplete_evidence_hold(self):
        i = inv(service_periods=("2026-08", "2026-09"))
        out = review_one_payment_invoice(pay(service_periods=("2026-09",)), i)
        self.assertIn("MULTIMONTH_SERVICE_COVERAGE_UNVERIFIED", out["blocker_codes"])

    def test_21_missing_service_period_proof_hold(self):
        out = review_one_payment_invoice(pay(service_periods=()), inv())
        self.assertIn("SERVICE_PERIOD_UNVERIFIED", out["blocker_codes"])

    def test_22_bank_date_before_invoice_date_hold(self):
        out = review_one_payment_invoice(pay(booked_at=date(2026, 8, 1)), inv())
        self.assertIn("BANK_DATE_PRECEDES_INVOICE", out["blocker_codes"])

    def test_23_missing_bank_date_hold(self):
        out = review_one_payment_invoice(pay(booked_at=None), inv())
        self.assertIn("SOURCE_DATE_EVIDENCE_MISSING", out["blocker_codes"])

    def test_24_client_identity_difference_hold(self):
        out = review_one_payment_invoice(pay(client="SYNTHETIC OTHER"), inv())
        self.assertIn("CLIENT_IDENTITY_NOT_VERIFIED", out["blocker_codes"])

    def test_25_non_exhaustive_amount_hypothesis_hold(self):
        out = review_one_payment_invoice(pay(credit="1160.01"), inv())
        self.assertIn("EXACT_GROSS_TDS_AMOUNT_NOT_PROVEN", out["blocker_codes"])

    def test_26_no_outstanding_invoice_hold(self):
        out = review_one_payment_invoice(pay(), inv(outstanding="0"))
        self.assertIn("NO_UNPAID_BALANCE", out["blocker_codes"])

    def test_27_no_real_invoice_identifier_can_enter_fixture(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_INVOICE_KEY_REQUIRED"):
            review_one_payment_invoice(pay(), inv(key="MXP19970"))

    def test_28_no_real_payment_row_identifier_can_enter_fixture(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_PAYMENT_KEY_REQUIRED"):
            review_one_payment_invoice(pay(key="14415"), inv())

    def test_29_dnm_dominant_near_is_review_only(self):
        out = dnm01_review("0.75", "3.00", 170)
        self.assertEqual(out["decision"], "DNM_HYPOTHESIS_REVIEW_ONLY")
        self.assertIsNone(out["financial_status"])
        self.assertFalse(out["allocation_executed"])

    def test_30_dnm_over_180_days_is_held(self):
        out = dnm01_review("0.75", "3.00", 181)
        self.assertIn("DNM_OVER_180_DAYS", out["blocker_codes"])

    def test_31_dnm_close_runner_up_is_held(self):
        out = dnm01_review("0.75", "2.50", 90)
        self.assertIn("DNM_RUNNER_UP_NOT_SEPARATED_BY_2_RUPEES", out["blocker_codes"])

    def test_32_dnm_best_more_than_1_is_held(self):
        out = dnm01_review("1.25", "4.00", 90)
        self.assertIn("DNM_BEST_NOT_WITHIN_1_RUPEE", out["blocker_codes"])

    def test_33_dnm_contradictory_reference_hold(self):
        out = dnm01_review("0.10", "4.00", 12, contradictory_ref=True)
        self.assertIn("DNM_CONTRADICTORY_MXP_REFERENCE", out["blocker_codes"])

    def test_34_dnm_missing_source_date_refused(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "DNM_SOURCE_DATE_EVIDENCE_REQUIRED"):
            dnm01_review("0.00", "3.00", -1)

    def test_35_decision_does_not_expose_invoice_id_or_amount(self):
        out = review_one_payment_invoice(pay(), inv())
        self.assertNotIn("SYN-MXP-001", repr(out))
        self.assertNotIn("1160.00", repr(out))
        self.assertNotIn("SYNTHETIC ALPHA", repr(out))


class R17ConservationShadowTests(unittest.TestCase):
    def test_36_two_payments_two_invoices_within_capacity_is_not_settlement(self):
        payments = [pay(), pay(key="SYN-PAY-002")]
        invoices = [inv(), inv(key="SYN-MXP-002")]
        edges = [edge(amount="100", payment="SYN-PAY-001", invoice="SYN-MXP-001"),
                 edge(amount="200", payment="SYN-PAY-002", invoice="SYN-MXP-002")]
        out = audit_shadow_reservations(payments, invoices, edges)
        self.assertTrue(out["capacity_constraints_passed"])
        self.assertFalse(out["v251_method_parity_certified"])
        self.assertEqual(out["real_payment_allocations"], 0)
        self.assertTrue(out["financial_apply_locked"])

    def test_37_bank_credit_over_reservation_fails(self):
        out = audit_shadow_reservations(
            [pay()],
            [inv(), inv(key="SYN-MXP-002")],
            [edge("1000", invoice="SYN-MXP-001"), edge("500", invoice="SYN-MXP-002")]
        )
        self.assertIn("PAYMENT_CREDIT_OVER_RESERVED", out["blocker_codes"])

    def test_38_invoice_outstanding_over_reservation_fails(self):
        out = audit_shadow_reservations(
            [pay(), pay(key="SYN-PAY-002")], [inv()],
            [edge("900", payment="SYN-PAY-001"), edge("900", payment="SYN-PAY-002")]
        )
        self.assertIn("INVOICE_BALANCE_OVER_RESERVED", out["blocker_codes"])

    def test_39_same_source_payment_row_duplicate_fails(self):
        out = audit_shadow_reservations([pay(), pay()], [inv()], [edge()])
        self.assertIn("DUPLICATE_BANK_SOURCE_ROW", out["blocker_codes"])

    def test_40_same_invoice_identifier_duplicate_fails(self):
        out = audit_shadow_reservations([pay()], [inv(), inv()], [edge()])
        self.assertIn("DUPLICATE_INVOICE_NUMBER", out["blocker_codes"])

    def test_41_identical_edge_repetition_fails(self):
        out = audit_shadow_reservations([pay()], [inv()], [edge(), edge()])
        self.assertIn("DUPLICATE_PROPOSED_EDGE", out["blocker_codes"])

    def test_42_unknown_source_row_fails(self):
        out = audit_shadow_reservations(
            [pay()], [inv()], [edge(payment="SYN-PAY-999")]
        )
        self.assertIn("UNKNOWN_SOURCE_ROW_OR_INVOICE", out["blocker_codes"])

    def test_43_protected_invoice_cannot_be_reserved(self):
        out = audit_shadow_reservations(
            [pay()], [inv(original_s_marker=0)], [edge()]
        )
        self.assertIn("INVOICE_S_NONBLANK_PROTECTED", out["blocker_codes"])

    def test_44_unapproved_cross_SOL_cannot_be_reserved(self):
        out = audit_shadow_reservations([pay()], [inv(sol="9002")], [edge()])
        self.assertIn("SBISA_OR_CROSS_SOL_UNAPPROVED", out["blocker_codes"])

    def test_45_client_conflict_cannot_be_reserved(self):
        out = audit_shadow_reservations(
            [pay()], [inv(client="SYNTHETIC OTHER")], [edge()]
        )
        self.assertIn("CLIENT_IDENTITY_CONFLICT", out["blocker_codes"])

    def test_46_negative_bank_credit_cannot_be_reserved(self):
        out = audit_shadow_reservations([pay(credit="-1")], [inv()], [edge()])
        self.assertIn("NONPOSITIVE_BANK_CREDIT", out["blocker_codes"])

    def test_47_carry_forward_source_status_is_not_certified(self):
        out = audit_shadow_reservations(
            [pay(original_bank_status="OK")], [inv()], [edge()]
        )
        self.assertIn("PRIOR_BANK_STATUS_NOT_REVALIDATED", out["blocker_codes"])

    def test_48_zero_and_negative_edge_rejected(self):
        for bad in ("0", "-1"):
            with self.subTest(bad=bad):
                out = audit_shadow_reservations([pay()], [inv()], [edge(bad)])
                self.assertIn("NONPOSITIVE_PROPOSED_RESERVATION", out["blocker_codes"])

    def test_49_reservation_more_than_two_decimals_is_refused(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "MONEY_MORE_THAN_TWO_DECIMALS"):
            audit_shadow_reservations([pay()], [inv()], [edge("0.001")])

    def test_50_empty_set_never_issues_payment_status(self):
        out = audit_shadow_reservations([], [], [])
        self.assertEqual(out["source_payment_rows"], 0)
        self.assertFalse(out["financial_statuses_written"])
        self.assertFalse(out["financial_database_connected"])

    def test_51_hypothesis_capacity_does_not_expose_source_keys_or_money(self):
        out = audit_shadow_reservations([pay()], [inv()], [edge()])
        self.assertNotIn("SYN-MXP-001", repr(out))
        self.assertNotIn("SYN-PAY-001", repr(out))
        self.assertNotIn("100.00", repr(out))
        self.assertFalse(out["amounts_and_source_ids_exposed"])

    def test_52_boolean_financial_amount_is_refused(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "MONEY_TYPE_UNSAFE"):
            audit_shadow_reservations([pay()], [inv()], [edge(True)])

    def test_53_non_synthetic_client_rejected(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_CLIENT_REQUIRED"):
            audit_shadow_reservations([pay(client="SBI")], [inv()], [edge()])

    def test_54_non_synthetic_invoice_reservation_rejected(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_INVOICE_KEY_REQUIRED"):
            audit_shadow_reservations([pay()], [inv()], [edge(invoice="MXP19970")])

    def test_55_gross_below_taxable_refused(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_GROSS_BELOW_TAXABLE"):
            review_one_payment_invoice(pay(), inv(gross="999", outstanding="999"))

    def test_56_outstanding_greater_than_gross_refused(self):
        with self.assertRaisesRegex(SyntheticOnlyRefusal, "SYNTHETIC_OUTSTANDING_EXCEEDS_GROSS"):
            review_one_payment_invoice(pay(), inv(outstanding="1200"))


if __name__ == "__main__":
    unittest.main()
