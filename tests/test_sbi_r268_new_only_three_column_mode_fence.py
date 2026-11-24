"""R26.8 new-only vs historical source fence, synthetic QA only."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_r268_new_only_three_column_mode_fence import (
    audit_intake_mode,review_new_only_rows,R268Refusal,NEW_HEADERS,HISTORICAL_SHEETS,
)
H="a"*64
def hist(**kw):
    return audit_intake_mode("HISTORICAL_XLSX_READONLY",HISTORICAL_SHEETS,
                             source_sha256=H,**kw)
def new(**kw):
    return audit_intake_mode("NEW_ONLY_THREE_COLUMN_REVIEW",NEW_HEADERS,
                             source_sha256=H,**kw)
def rows(data=None,**kw):
    return review_new_only_rows(
        [("SYNTHETIC POSTAGE","0001","1160.00")] if data is None else data,
        source_sha256=H,**kw,
    )
class R268ReadOnlyModeGateTests(unittest.TestCase):
    def test_01_old_workbook_readonly_not_finance(self):
        r=hist()
        self.assertFalse(r["real_historical_payment_allocation_authorized"])
        self.assertTrue(r["financial_apply_locked"])
    def test_02_new_three_column_schema(self):
        r=new()
        self.assertEqual(r["mode"],"NEW_ONLY_THREE_COLUMN_REVIEW")
        self.assertFalse(r["release_authorized"])
    def test_03_new_no_bank_date_column(self):
        self.assertFalse(new()["bank_date_column_in_upload"])
    def test_04_new_no_utr_column(self):
        self.assertFalse(new()["bank_utr_column_in_upload"])
    def test_05_missing_activation_cutoff_stays_none(self):
        self.assertIsNone(new()["new_only_cutoff_ist"])
    def test_06_confirmed_cutoff_is_syntax_only(self):
        r=new(cutoff_ist="2026-11-24T12:34:56+05:30")
        self.assertEqual(r["new_only_cutoff_ist"],"2026-11-24T12:34:56+05:30")
        self.assertFalse(r["release_authorized"])
    def test_07_cutoff_without_timezone_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"CUTOFF_NOT_IST"):
            new(cutoff_ist="2026-11-24T12:34:56")
    def test_08_cutoff_utc_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"CUTOFF_NOT_IST"):
            new(cutoff_ist="2026-11-24T07:04:56+00:00")
    def test_09_cutoff_wrong_type_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"CUTOFF_NOT_TEXT"):
            new(cutoff_ist=123)
    def test_10_cutoff_bad_date_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"CUTOFF_INVALID"):
            new(cutoff_ist="2026-13-99T25:00:00+05:30")
    def test_11_declaring_bank_proof_does_not_certify_it(self):
        r=new(cutoff_ist="2026-11-24T12:00:00+05:30",
              declared_bank_utr_present=True,
              bank_origin_independently_authenticated=True)
        self.assertFalse(r["independently_verified_bank_origin"])
        self.assertEqual(r["new_only_rows_eligible_for_financial_settlement"],0)
    def test_12_nonboolean_bank_flag_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"BANK_EVIDENCE_BOOLEAN_REQUIRED"):
            new(declared_bank_utr_present="true")
    def test_13_nonboolean_auth_flag_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"BANK_EVIDENCE_BOOLEAN_REQUIRED"):
            new(bank_origin_independently_authenticated=1)
    def test_14_hist_cannot_inherit_new_only_cutoff(self):
        with self.assertRaisesRegex(R268Refusal,"HISTORICAL_INPUT_CANNOT_SET_NEW_ONLY_CUTOFF"):
            hist(cutoff_ist="2026-11-24T12:00:00+05:30")
    def test_15_wrong_history_sheet_order_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"HISTORICAL_SHEET_IDENTITY_MISMATCH"):
            audit_intake_mode("HISTORICAL_XLSX_READONLY",("PAYMNENT","Invoice Details."),
                              source_sha256=H)
    def test_16_wrong_historical_spelling_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"HISTORICAL_SHEET_IDENTITY_MISMATCH"):
            audit_intake_mode("HISTORICAL_XLSX_READONLY",("Invoice Details.","PAYMENT"),
                              source_sha256=H)
    def test_17_wrong_new_extra_column_rejected(self):
        with self.assertRaisesRegex(R268Refusal,"NEW_ONLY_EXACT_THREE_COLUMN"):
            audit_intake_mode("NEW_ONLY_THREE_COLUMN_REVIEW",
                ("Description","SOL ID","Credit Amount","UTR"),source_sha256=H)
    def test_18_new_only_no_old_bank_K_model_fields(self):
        with self.assertRaisesRegex(R268Refusal,"NEW_ONLY_EXACT_THREE_COLUMN"):
            audit_intake_mode("NEW_ONLY_THREE_COLUMN_REVIEW",
                ("Description","Branch Code","Credit"),source_sha256=H)
    def test_19_inferred_unknown_mode_refused(self):
        with self.assertRaisesRegex(R268Refusal,"EXPLICIT_INTAKE_MODE_REQUIRED"):
            audit_intake_mode("AUTO",NEW_HEADERS,source_sha256=H)
    def test_20_no_source_hash_refused(self):
        with self.assertRaisesRegex(R268Refusal,"EXACT_SOURCE_SHA_REQUIRED"):
            audit_intake_mode("NEW_ONLY_THREE_COLUMN_REVIEW",NEW_HEADERS,source_sha256="bad")
    def test_21_financial_apply_never_enabled(self):
        with self.assertRaisesRegex(R268Refusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            new(financial_apply="ENABLED")
    def test_22_three_exact_fields_supported_for_review(self):
        r=rows()
        self.assertEqual(r["format_candidates_only"],1)
        self.assertEqual(r["real_bank_credits_allocated"],0)
    def test_23_numeric_SOL_rejected(self):
        r=rows([("SYN POSTAGE",1,"10.00")])
        self.assertIn((2,"SOL_MUST_BE_EXACT_TEXT"),r["hold_reasons"])
    def test_24_zero_padded_SOL_not_changed(self):
        self.assertEqual(rows([("SYN POSTAGE","0001","10.00")])["format_candidates_only"],1)
    def test_25_subpaise_credit_held(self):
        self.assertIn((2,"CREDIT_SUBPAISE_UNVERIFIED"),
                      rows([("SYN POSTAGE","0001","10.001")])["hold_reasons"])
    def test_26_credit_float_rejected(self):
        self.assertIn((2,"CREDIT_MUST_BE_EXACT_DECIMAL"),
                      rows([("SYN POSTAGE","0001",10.01)])["hold_reasons"])
    def test_27_bad_bank_credit_text_held(self):
        self.assertIn((2,"CREDIT_NOT_NUMERIC"),
                      rows([("SYN POSTAGE","0001","Credit")])["hold_reasons"])
    def test_28_negative_credit_held(self):
        self.assertIn((2,"CREDIT_NONPOSITIVE"),
                      rows([("SYN POSTAGE","0001","-1.00")])["hold_reasons"])
    def test_29_zero_credit_held(self):
        self.assertIn((2,"CREDIT_NONPOSITIVE"),
                      rows([("SYN POSTAGE","0001","0.00")])["hold_reasons"])
    def test_30_missing_description_held(self):
        self.assertIn((2,"DESCRIPTION_REQUIRED"),
                      rows([("","0001","10.00")])["hold_reasons"])
    def test_31_missing_bank_SOL_held(self):
        self.assertIn((2,"SOL_MUST_BE_EXACT_TEXT"),
                      rows([("SYN POSTAGE","","10.00")])["hold_reasons"])
    def test_32_extra_field_row_held(self):
        self.assertIn((2,"REQUIRES_EXACT_THREE_FIELDS"),
                      rows([("SYN POSTAGE","0001","10.00","UTR")])["hold_reasons"])
    def test_33_duplicate_looking_rows_not_classified(self):
        r=rows([("SYN POSTAGE","0001","10.00")]*2)
        self.assertEqual(r["format_candidates_only"],2)
        self.assertEqual(r["financial_statuses_created"],0)
    def test_34_new_only_production_stays_locked_with_rows(self):
        r=rows()
        self.assertFalse(r["release_authorized"])
        self.assertEqual(r["production_database_writes"],0)
    def test_35_new_only_historical_ok_copy_forbidden(self):
        self.assertFalse(rows()["reconciliation_or_older_status_copy_permitted"])
    def test_36_missing_transaction_provenance_blocks(self):
        r=rows()
        self.assertFalse(r["authenticated_bank_transaction_date_available"])
        self.assertFalse(r["authenticated_utr_unique_event_available"])
    def test_37_empty_rows_still_no_statuses(self):
        r=rows([])
        self.assertEqual(r["rows_seen"],0)
        self.assertEqual(r["financial_statuses_created"],0)
    def test_38_bad_row_structure_rejected_at_row_level(self):
        r=rows([None])
        self.assertIn((2,"REQUIRES_EXACT_THREE_FIELDS"),r["hold_reasons"])
    def test_39_nonpositive_padded_amount_never_applied(self):
        r=rows([("SYN POSTAGE","0001","0.00")])
        self.assertFalse(r["release_authorized"])
    def test_40_separate_history_and_new_only(self):
        self.assertNotEqual(new()["mode"],hist()["mode"])
        self.assertEqual(new()["financial_statuses_created"],0)
        self.assertEqual(hist()["financial_statuses_created"],0)
if __name__=="__main__":unittest.main()
