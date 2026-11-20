"""D-027: fabricated-only future payment evidence intake review tests."""
import copy
import importlib.util
from pathlib import Path
import unittest

base = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "synthetic_payment_evidence", base / "synthetic_payment_evidence.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def record(payment_id="SYNTH-PAY-A", *, credit="117.00",
           sol="1505", sbisa=False, pay_date="2026-12-02",
           utr="SYNTH-UTR-ABC123", narration="SYNTH bulk postage Dec-26",
           ref="SYNTH-INV-A", proof=True):
    original = [""] * 12
    original[8] = credit
    original[2] = "SYNTHETIC BANK NARRATION"
    return {
        "source_kind": "SYNTHETIC", "payment_id": payment_id,
        "original_A_to_L": original, "payment_date": pay_date,
        "sol_id": sol, "sbisa": sbisa, "utr": utr,
        "narration": narration, "invoice_ref": ref,
        "proof_name": "SYNTH-bank.xlsx" if proof else None,
        "proof_sha256": "a" * 64 if proof else None,
    }


def simulate(rows=None, **changes):
    options = dict(
        activation_date="2026-12-01", submitted_date="2026-12-03",
        actor_id="SYNTH-USER-ADMIN", mock_role="SYNTHETIC_PAYMENT_EVIDENCE_UPLOADER",
        existing_synthetic_receipts=[], synthetic_mode=True,
    )
    options.update(changes)
    return mod.preview_synthetic_new_evidence(
        [record()] if rows is None else rows, **options)


class SyntheticPaymentEvidenceTests(unittest.TestCase):
    def test_new_row_preview_is_not_a_real_upload_or_allocation(self):
        rows = [record()]
        original = copy.deepcopy(rows)
        result = simulate(rows)
        self.assertEqual(result["preview_ready_count"], 1)
        self.assertEqual(result["held_count"], 0)
        self.assertEqual(result["preview_rows"][0]["status"], "PREVIEW_READY_NOT_IMPORTED")
        self.assertFalse(result["payment_file_uploaded"])
        self.assertFalse(result["persistent_receipts_created"])
        self.assertFalse(result["historical_records_accessed"])
        self.assertFalse(result["live_financial_writes"])
        self.assertFalse(result["approved_for_import"])
        self.assertEqual(rows, original)

    def test_credit_column_i_strict_ignores_other_credit_like_cells(self):
        row = record(credit="")
        row["original_A_to_L"][7] = "999.99"
        result = simulate([row])
        self.assertEqual(result["held_count"], 1)
        self.assertEqual(result["holds"][0]["reason"],
                         "ORIGINAL_COLUMN_I_CREDIT_INVALID")

    def test_money_zero_negative_formula_nan_bad_precision_hold(self):
        for raw in ("0", "-1.00", "NaN", "=1+2", "15.999", "", "1,000.00"):
            with self.subTest(raw=raw):
                result = simulate([record(credit=raw)])
                self.assertEqual(result["preview_ready_count"], 0)
                self.assertEqual(result["held_count"], 1)

    def test_original_a_to_l_immutability_and_width(self):
        bad = record()
        bad["original_A_to_L"] = [""] * 11
        out = simulate([bad])
        self.assertEqual(out["holds"][0]["reason"], "ORIGINAL_A_TO_L_REQUIRED")

    def test_duplicate_source_two_rows_both_held(self):
        row = record()
        out = simulate([row, copy.deepcopy(row)])
        self.assertEqual(out["preview_ready_count"], 0)
        self.assertEqual(out["held_count"], 2)
        self.assertTrue(all(x["reason"] == "DUPLICATE_PAYMENT_ID" for x in out["holds"]))

    def test_repeated_utr_with_different_payment_ids_both_held(self):
        out = simulate([record(), record(payment_id="SYNTH-PAY-B", credit="50.00")])
        self.assertEqual(out["preview_ready_count"], 0)
        self.assertEqual(out["held_count"], 2)
        self.assertTrue(all(x["reason"] == "DUPLICATE_OR_CONFLICTING_UTR_IN_BATCH"
                            for x in out["holds"]))

    def test_existing_receipt_unchanged_payload_is_not_accepted_again(self):
        previous = simulate()["preview_receipts"]
        out = simulate(existing_synthetic_receipts=previous)
        self.assertEqual(out["preview_ready_count"], 0)
        self.assertEqual(out["holds"][0]["reason"], "ALREADY_PREVIEWED_EVIDENCE")

    def test_existing_receipt_same_utr_different_credit_blocked(self):
        previous = simulate()["preview_receipts"]
        out = simulate([record(payment_id="SYNTH-PAY-B", credit="99.00")],
                       existing_synthetic_receipts=previous)
        self.assertEqual(out["preview_ready_count"], 0)
        self.assertEqual(out["holds"][0]["reason"], "EXISTING_UTR_CONFLICT")

    def test_real_or_legacy_receipts_not_usable_as_index(self):
        old = dict(simulate()["preview_receipts"][0])
        old["source_kind"] = "REAL"
        with self.assertRaises(mod.EvidenceIntakeBlocked):
            simulate(existing_synthetic_receipts=[old])

    def test_real_bank_and_real_invoice_identifiers_rejected(self):
        for target, value in (
            ("source_kind", "REAL"),
            ("payment_id", "SBI-BANK-1"),
            ("utr", "REALUTR123"),
            ("invoice_ref", "MXP21569"),
        ):
            with self.subTest(field=target):
                row = record()
                row[target] = value
                out = simulate([row])
                self.assertEqual(out["preview_ready_count"], 0)

    def test_activation_date_blocks_earlier_payment(self):
        out = simulate([record(pay_date="2026-11-30")])
        self.assertEqual(out["holds"][0]["reason"], "PRE_ACTIVATION_PAYMENT_FORBIDDEN")

    def test_future_payment_date_blocked(self):
        out = simulate([record(pay_date="2026-12-04")])
        self.assertEqual(out["holds"][0]["reason"], "FUTURE_BANK_CREDIT_FORBIDDEN")

    def test_submission_before_activation_denied(self):
        with self.assertRaises(mod.EvidenceIntakeBlocked):
            simulate(submitted_date="2026-11-30")

    def test_no_live_auth_claim_and_no_synthetic_optin_denied(self):
        for override in (
            {"mock_role": "ADMIN"},
            {"actor_id": "REAL_USER"},
            {"synthetic_mode": False},
            {"synthetic_mode": "True"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(mod.EvidenceIntakeBlocked):
                    simulate(**override)

    def test_sbisa_blank_sol_only_explicitly_marked(self):
        valid = simulate([record(sol="", sbisa=True)])
        self.assertEqual(valid["preview_ready_count"], 1)
        bad = simulate([record(sol="", sbisa=False)])
        self.assertEqual(bad["holds"][0]["reason"], "SOL_REQUIRED")

    def test_proof_metadata_only_not_file_access(self):
        out = simulate([record(proof=False)])
        self.assertEqual(out["preview_ready_count"], 1)
        wrong = record()
        wrong["proof_name"] = "SYNTH-bank.exe"
        self.assertEqual(simulate([wrong])["holds"][0]["reason"], "PROOF_METADATA_INVALID")

    def test_partial_batch_returns_only_ordinal_reason(self):
        a = record()
        b = record(payment_id="SYNTH-PAY-B", utr="SYNTH-UTR-DEF456", credit="abc")
        out = simulate([a, b])
        self.assertEqual(out["preview_ready_count"], 1)
        self.assertEqual(out["held_count"], 1)
        self.assertEqual(out["holds"][0]["source_row_ordinal"], 2)
        self.assertNotIn("SYNTH-UTR", str(out["holds"]))

    def test_unknown_source_columns_fail_closed(self):
        row = record()
        row["credit_override"] = "100000.00"
        self.assertEqual(simulate([row])["holds"][0]["reason"], "EVIDENCE_SCHEMA_MISMATCH")

    def test_batch_size_guard(self):
        with self.assertRaises(mod.EvidenceIntakeBlocked):
            simulate([])
        with self.assertRaises(mod.EvidenceIntakeBlocked):
            simulate([record()] * 101)


if __name__ == "__main__":
    unittest.main()
