"""D-030 synthetic-only post-activation bank provenance / future-only QA."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "d030_future_payment_provenance",
    ROOT / "staging/aws_login_v150/d030_future_payment_provenance.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(*, desc="SYNTH-POSTAGE AUG-26", sol="001505", credit="117.00"):
    return {"Description": desc, "SOL ID": sol, "Credit Amount": credit}


def metadata(source, *, excel_row=2, bank_date="2026-12-02",
             reference="SYNTH-UTR-001", source_credit="117.00",
             source_column="PAYMNENT!I"):
    return {
        "source_kind": "SYNTHETIC",
        "excel_row": excel_row,
        "bank_date": bank_date,
        "bank_reference": reference,
        "source_credit_column": source_column,
        "source_credit_I": source_credit,
        "evidence_row_sha256": mod.evidence_row_sha256(source),
    }


def check(rows=None, sidecar=None, **changes):
    source = [row()] if rows is None else rows
    metadata_rows = [metadata(source[0])] if sidecar is None else sidecar
    args = dict(mock_activation_date="2026-12-01",
                mock_submission_date="2026-12-03",
                previous_synthetic_references=(), synthetic_mode=True)
    args.update(changes)
    return mod.preview_future_evidence(source, metadata_rows, **args)


class D030FutureOnlyProvenanceTests(unittest.TestCase):
    def test_synthetic_good_row_exact_existing_3_column_headers(self):
        source = [row()]
        sidecar = [metadata(source[0])]
        original_source, original_meta = copy.deepcopy(source), copy.deepcopy(sidecar)
        result = check(source, sidecar)
        self.assertEqual(result["mode"], "SYNTHETIC_ONLY")
        self.assertEqual(result["preview_ready_count"], 1)
        self.assertEqual(result["held_row_count"], 0)
        self.assertFalse(result["production_unlock_allowed"])
        self.assertFalse(result["financial_reconciliation_executed"])
        self.assertFalse(result["financial_write_performed"])
        self.assertFalse(result["historical_data_accessed"])
        self.assertFalse(result["source_credit_I_claim_verified_against_bank"])
        self.assertFalse(result["real_user_authenticated"])
        self.assertEqual(source, original_source)
        self.assertEqual(sidecar, original_meta)

    def test_double_row_unique_reference_allowed_as_mock_preview(self):
        rows = [row(), row(desc="SYNTH-POSTAGE SEP-26", sol="1", credit="25.50")]
        side = [metadata(rows[0]), metadata(rows[1], excel_row=3,
                        reference="SYNTH-UTR-002", source_credit="25.50")]
        self.assertEqual(check(rows, side)["preview_ready_count"], 2)

    def test_cutoff_blocks_old_payment_even_with_new_submission(self):
        m = metadata(row(), bank_date="2026-11-30")
        result = check(sidecar=[m])
        self.assertEqual(result["preview_ready_count"], 0)
        self.assertEqual(result["held_row_count"], 1)
        self.assertIn("PRE_ACTIVATION_BANK_DATE_FORBIDDEN", result["holds"][0]["reasons"])

    def test_future_dated_bank_entry_blocked(self):
        m = metadata(row(), bank_date="2026-12-04")
        self.assertIn("FUTURE_BANK_DATE_FORBIDDEN", check(sidecar=[m])["holds"][0]["reasons"])

    def test_false_or_mock_release_cannot_be_used_for_real(self):
        for synthetic_mode in (False, "True", None):
            with self.subTest(mode=synthetic_mode):
                with self.assertRaises(mod.FutureEvidenceBlocked):
                    check(synthetic_mode=synthetic_mode)
        with self.assertRaises(mod.FutureEvidenceBlocked):
            check(mock_submission_date="2026-11-29")

    def test_wrong_references_and_real_bank_fields_are_held(self):
        for key, value, expected in (
            ("source_kind", "REAL", "REAL_BANK_PROVENANCE_FORBIDDEN"),
            ("bank_reference", "ACTUAL-UTR-123", "BANK_REFERENCE_INVALID"),
            ("bank_reference", "20261202", "BANK_REFERENCE_INVALID"),
            ("source_credit_column", "PAYMNENT!H", "ORIGINAL_CREDIT_I_LINEAGE_REQUIRED"),
            ("source_credit_I", "116.00", "ORIGINAL_CREDIT_I_MISMATCH"),
            ("source_credit_I", "bad", "ORIGINAL_CREDIT_I_INVALID"),
            ("bank_date", "02/12/2026", "BANK_DATE_INVALID"),
            ("excel_row", 5, "ROW_ORDINAL_MISMATCH"),
        ):
            with self.subTest(field=key, value=value):
                m = metadata(row())
                m[key] = value
                result = check(sidecar=[m])
                self.assertIn(expected, result["holds"][0]["reasons"])
                self.assertEqual(result["preview_ready_count"], 0)

    def test_sidecar_digest_protects_three_column_reordering(self):
        m = metadata(row())
        m["evidence_row_sha256"] = "0" * 64
        result = check(sidecar=[m])
        self.assertIn("EVIDENCE_ROW_DIGEST_MISMATCH", result["holds"][0]["reasons"])

    def test_invalid_provenance_unknown_keys_are_held(self):
        m = metadata(row())
        m["trusted_bank_writer"] = True
        result = check(sidecar=[m])
        self.assertIn("PROVENANCE_SCHEMA_MISMATCH", result["holds"][0]["reasons"])

    def test_missing_sidecar_denied(self):
        with self.assertRaises(mod.FutureEvidenceBlocked):
            check(sidecar=[])

    def test_real_or_malformed_three_column_source_denied(self):
        for source in (
            {"Description": "REAL BANK POSTING", "SOL ID": "001505", "Credit Amount": "117.00"},
            {"Description": "SYNTH-POSTAGE AUG-26", "SOL ID": 1505, "Credit Amount": "117.00"},
            {"Description": "SYNTH-POSTAGE AUG-26", "SOL ID": "001505",
             "Credit Amount": "117.00", "Payment Date": "2026-12-02"},
        ):
            with self.subTest(source=source):
                result = check(rows=[source], sidecar=[{
                    "source_kind":"SYNTHETIC", "excel_row":2, "bank_date":"2026-12-02",
                    "bank_reference":"SYNTH-UTR-001",
                    "source_credit_column":"PAYMNENT!I",
                    "source_credit_I":"117.00",
                    "evidence_row_sha256":"0"*64,
                }])
                self.assertEqual(result["preview_ready_count"], 0)
                self.assertIn("EXACT_EXISTING_3_COLUMN_FORMAT_REQUIRED"
                              if len(source)!=3 else
                              "SYNTHETIC_DESCRIPTION_REQUIRED"
                              if source["Description"].startswith("REAL") else
                              "SOL_TEXT_REQUIRED", result["holds"][0]["reasons"])

    def test_credit_invalid_or_formula_cannot_be_previewed(self):
        for credit in ("", "-1", "0", "=100+17", "NaN", "1,200", "1.234", 117.0):
            with self.subTest(credit=credit):
                r = row(credit=credit)
                result = check(rows=[r], sidecar=[{
                    "source_kind":"SYNTHETIC", "excel_row":2, "bank_date":"2026-12-02",
                    "bank_reference":"SYNTH-UTR-001",
                    "source_credit_column":"PAYMNENT!I",
                    "source_credit_I":"117.00",
                    "evidence_row_sha256":"0"*64,
                }])
                self.assertIn("MONEY_AS_STRICT_TEXT_REQUIRED" if credit not in ("0",)
                              else "POSITIVE_FINITE_CREDIT_REQUIRED",
                              result["holds"][0]["reasons"])

    def test_duplicate_utr_both_rows_held_atomically(self):
        rows = [row(), row(desc="SYNTH-SEP CREDIT", credit="40.00")]
        m = [metadata(rows[0]),
             metadata(rows[1], excel_row=3, source_credit="40.00")]
        result = check(rows, m)
        self.assertEqual(result["preview_ready_count"], 0)
        self.assertEqual(result["held_row_count"], 2)
        self.assertTrue(all("DUPLICATE_BANK_REFERENCE_IN_BATCH" in x["reasons"]
                            for x in result["holds"]))

    def test_duplicate_source_rows_even_with_unique_utr_held(self):
        rows = [row(), copy.deepcopy(row())]
        m = [metadata(rows[0]), metadata(rows[1], excel_row=3,
                      reference="SYNTH-UTR-002")]
        result = check(rows, m)
        self.assertEqual(result["preview_ready_count"], 0)
        self.assertTrue(all("DUPLICATE_THREE_COLUMN_SOURCE_ROW" in x["reasons"]
                            for x in result["holds"]))

    def test_prior_mock_reference_conflict(self):
        seen = [{
            "source_kind": "SYNTHETIC",
            "bank_reference_sha256": mod._reference_hash("SYNTH-UTR-001"),
        }]
        result = check(previous_synthetic_references=seen)
        self.assertIn("PRIOR_SYNTHETIC_REFERENCE_CONFLICT", result["holds"][0]["reasons"])
        self.assertEqual(result["preview_ready_count"], 0)

    def test_real_prior_reference_index_rejected_entire_batch(self):
        with self.assertRaises(mod.FutureEvidenceBlocked):
            check(previous_synthetic_references=[{
                "source_kind": "LIVE",
                "bank_reference_sha256": "a" * 64,
            }])

    def test_single_bad_row_prevents_other_row_preview(self):
        rows = [row(), row(desc="SYNTH-SECOND", credit="50.00")]
        side = [metadata(rows[0]), metadata(rows[1], excel_row=3,
                    reference="SYNTH-UTR-002", source_credit="49.00")]
        result = check(rows, side)
        self.assertEqual(result["source_rows"], 2)
        self.assertEqual(result["held_row_count"], 1)
        self.assertEqual(result["preview_ready_count"], 0)
        self.assertEqual(result["status"], "HELD_ATOMICALLY_NO_RECONCILIATION")

    def test_oversized_batch_denied(self):
        with self.assertRaises(mod.FutureEvidenceBlocked):
            check(rows=[row()] * 101, sidecar=[metadata(row())] * 101)

    def test_source_lineage_is_not_certified_from_self_attestation(self):
        response = check()
        self.assertFalse(response["source_credit_I_claim_verified_against_bank"])
        self.assertFalse(response["live_payment_uniqueness_certified"])
        self.assertFalse(response["mock_cutoff_is_real_release_cutoff"])
        self.assertEqual(response["source_sheet_original"], "NOT_ACCESSED")
        self.assertFalse(response["invoice_or_payment_db_accessed"])
        self.assertFalse(response["receipt_persisted"])


if __name__ == "__main__":
    unittest.main()
