"""Case 1: approved SBI full-bank header mapping (SYNTHETIC fixtures only)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/ci"))
from sbi_case1_payment_header_mapper import (
    map_payment_headers, canonical_payment_row,
    HeaderMappingRefusal,APPROVED_PAYMENT_HEADERS,
)

LEGACY=("Location","Branch Name","Txn Date","Value Date","Description",
        "Branch Code","Name","        Debit","Credit","Balance",
        "Record For Me")
APPROVED=APPROVED_PAYMENT_HEADERS
H_CREDIT=("Location","Branch Name","Txn Date","Value Date","Description",
          "Branch Code","Name","Credit", "", "", "Record For Me")


class Case1HeaderMappingTests(unittest.TestCase):
    def test_01_legacy_description_E_maps_to_approved_A(self):
        self.assertEqual(map_payment_headers(LEGACY).column("Description"),5)
    def test_02_legacy_credit_I_maps_to_approved_I(self):
        self.assertEqual(map_payment_headers(LEGACY).column("Credit"),9)
    def test_03_other_historical_credit_H_maps_to_approved_I(self):
        self.assertEqual(map_payment_headers(H_CREDIT).column("Credit"),8)
    def test_04_approved_description_A_maps_to_A(self):
        self.assertEqual(map_payment_headers(APPROVED).column("Description"),1)
    def test_05_approved_credit_I_maps_to_I(self):
        self.assertEqual(map_payment_headers(APPROVED).column("Credit"),9)
    def test_06_approved_service_period_C(self):
        self.assertEqual(map_payment_headers(APPROVED).column("Service Period"),3)
    def test_07_approved_bank_reference_D(self):
        self.assertEqual(map_payment_headers(APPROVED).column("Bank Reference / UTR"),4)
    def test_08_approved_statement_source_E(self):
        self.assertEqual(map_payment_headers(APPROVED).column("Bank / Statement Source"),5)
    def test_09_legacy_txn_date_C_maps_to_posting_date_B(self):
        self.assertEqual(map_payment_headers(LEGACY).column("Posting Date"),3)
    def test_10_value_date_not_silently_posting(self):
        x=map_payment_headers(LEGACY)
        self.assertIn((4,"Value Date"),x.ignored_headers)
        self.assertEqual(x.column("Posting Date"),3)
    def test_11_legacy_branch_name_not_client_name(self):
        x=map_payment_headers(LEGACY)
        self.assertIn((2,"Branch Name"),x.ignored_headers)
        self.assertEqual(x.column("Client Name"),7)
    def test_12_legacy_location_not_bank_source(self):
        x=map_payment_headers(LEGACY)
        self.assertIsNone(x.column("Bank / Statement Source"))
    def test_13_legacy_source_UTR_missing_not_invented(self):
        x=map_payment_headers(LEGACY)
        self.assertIsNone(x.column("Bank Reference / UTR"))
        self.assertIn("Bank Reference / UTR",x.missing_fields)
    def test_14_legacy_service_period_missing_not_from_date(self):
        x=map_payment_headers(LEGACY)
        self.assertIsNone(x.column("Service Period"))
    def test_15_legacy_Record_For_Me_K_preserved(self):
        self.assertEqual(map_payment_headers(LEGACY).column("Record For Me"),11)
    def test_16_moved_Record_For_Me_L_read_by_name(self):
        a=list(LEGACY);a[10]="";a.append("Record For Me")
        self.assertEqual(map_payment_headers(a).column("Record For Me"),12)
    def test_17_no_history_population_equality_requirement(self):
        x=map_payment_headers(LEGACY).audit()
        self.assertFalse(x["historical_row_count_parity_required"])
        self.assertFalse(x["historical_OK_status_copying_permitted"])
    def test_18_no_physical_source_reorder_claim(self):
        self.assertFalse(map_payment_headers(LEGACY).audit()["records_physically_reordered"])
    def test_19_canonical_row_moves_values_without_editing_source(self):
        src={3:"2026-11-24",5:"SYNTHETIC POSTAGE",6:"0001",
             7:"SYNTHETIC ALPHA",8:"",9:"1160.00",11:""}
        before=dict(src)
        out=canonical_payment_row(src,map_payment_headers(LEGACY))
        self.assertEqual(out[0],"SYNTHETIC POSTAGE")
        self.assertEqual(out[1],"2026-11-24")
        self.assertEqual(out[5],"0001")
        self.assertEqual(out[8],"1160.00")
        self.assertIsNone(out[2])
        self.assertEqual(src,before)
    def test_20_credit_H_not_legacy_I(self):
        src={3:"2026-11-24",5:"SYNTHETIC POSTAGE",
             6:"0001",7:"SYNTHETIC ALPHA",8:"90.00",9:"999999"}
        out=canonical_payment_row(src,map_payment_headers(H_CREDIT))
        self.assertEqual(out[8],"90.00")
        self.assertNotEqual(out[8],"999999")
    def test_21_approved_order_full(self):
        src={n:f"V{n}" for n in range(1,12)}
        self.assertEqual(canonical_payment_row(src,map_payment_headers(APPROVED)),
                         tuple(f"V{n}" for n in range(1,12)))
    def test_22_shuffled_approved_order_full(self):
        a=list(APPROVED)
        a.reverse()
        x=map_payment_headers(a)
        src={n:f"V{n}" for n in range(1,12)}
        out=canonical_payment_row(src,x)
        self.assertEqual(out[0],"V11")
        self.assertEqual(out[8],"V3")
    def test_23_case_and_extra_spaces_accepted(self):
        x=map_payment_headers(["  Description ","BRANCH CODE","  Credit  ","TXN DATE"])
        self.assertEqual(x.column("Credit"),3)
    def test_24_header_noise_does_not_change_credit(self):
        x=map_payment_headers(["Credit", "Debit", "Total", "SOL ID","Narration"])
        self.assertEqual(x.column("Credit"),1)
    def test_25_missing_credit_refused_not_assumed_I(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"REQUIRED_BANK_HEADER_MISSING"):
            map_payment_headers(["Description","SOL ID","Debit","Balance"])
    def test_26_missing_SOL_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"REQUIRED_BANK_HEADER_MISSING"):
            map_payment_headers(["Description","Credit","Client Name"])
    def test_27_missing_description_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"REQUIRED_BANK_HEADER_MISSING"):
            map_payment_headers(["Credit","SOL ID"])
    def test_28_duplicate_credit_aliases_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"DUPLICATE_OR_AMBIGUOUS"):
            map_payment_headers(["Description","SOL ID","Credit","Credit Amount"])
    def test_29_duplicate_SOL_aliases_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"DUPLICATE_OR_AMBIGUOUS"):
            map_payment_headers(["Description","SOL ID","Branch Code","Credit"])
    def test_30_no_fuzzy_typo_autocorrection(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"REQUIRED_BANK_HEADER_MISSING"):
            map_payment_headers(["Description","SOL ID","Creit"])
    def test_31_new_only_upload_not_treated_full_bank(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"NEW_ONLY_UPLOAD_REQUIRES_SEPARATE"):
            map_payment_headers(["Description","SOL ID","Credit Amount"])
    def test_32_unknown_mode_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"FULL_BANK_MODE_ONLY"):
            map_payment_headers(LEGACY,explicit_mode="NEW_ONLY")
    def test_33_financial_apply_unlock_refused(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"FINANCIAL_APPLY_LOCK_REQUIRED"):
            map_payment_headers(LEGACY,financial_apply="ENABLED")
    def test_34_posting_date_required_for_full_financial_read(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"BANK_POSTING_DATE_HEADER_REQUIRED"):
            map_payment_headers(["Description","SOL ID","Credit"],
                                require_posting_date=True)
    def test_35_missing_date_allowed_as_review_not_full(self):
        x=map_payment_headers(["Description","SOL ID","Credit","Balance","Client Name"])
        self.assertFalse(x.eligible_for_full_bank_import)
    def test_36_legacy_with_Txn_Date_can_be_read_as_full(self):
        x=map_payment_headers(LEGACY,require_posting_date=True)
        self.assertTrue(x.eligible_for_full_bank_import)
    def test_37_approved_template_can_be_read_as_full(self):
        self.assertTrue(map_payment_headers(APPROVED,require_posting_date=True).eligible_for_full_bank_import)
    def test_38_do_not_infer_credit_from_amount_header(self):
        with self.assertRaisesRegex(HeaderMappingRefusal,"REQUIRED_BANK_HEADER_MISSING"):
            map_payment_headers(["Description","SOL ID","Amount"])
    def test_39_other_custom_columns_preserved_in_mapping_audit(self):
        x=map_payment_headers(list(APPROVED)+["SYNTHETIC CUSTOM TAG"])
        self.assertEqual(x.ignored_headers[-1][1],"SYNTHETIC CUSTOM TAG")
    def test_40_audit_never_claims_finance_release(self):
        x=map_payment_headers(APPROVED).audit()
        self.assertTrue(x["financial_apply_locked"])
        self.assertEqual(x["production_database_writes"],0)

if __name__=="__main__":unittest.main()
