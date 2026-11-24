"""R16 fully synthetic, in-memory tests — never run on live financial data."""
import hashlib
import io
import sys
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from sbi_r16_master_identity_shadow import (
    IdentityGateRefused, shadow_identity_preflight,
)


def workbook_bytes(workbook):
    data = io.BytesIO()
    workbook.save(data)
    return data.getvalue()


def source_workbook():
    book = Workbook()
    inv = book.active
    inv.title = "Invoice Details."
    for col in range(1, 35):
        inv.cell(1, col, "UNMODIFIED_" + str(col))
    inv["G1"], inv["H1"], inv["J1"], inv["M1"] = "Branch Code", "Client Name", "Invoice No", "SGST"
    rows = [
        ("00001", "BRANCH ALPHA", "MXP10001", None),
        ("00002", "STATE BANK OF INDIA", "MXP10002", None),
        ("00001", "BRANCH ALPHA", "MXP10003", "PAID"),
        ("00004", "BRANCH GAMMA", "MXP10004", None),
        ("00002", "BRANCH BETA", "MXP10005", None),
        ("00002", "BRANCH BETA", "MXP10005", None),
    ]
    for i, (sol, client, invoice, status) in enumerate(rows, start=2):
        inv.cell(i, 7, sol)
        inv.cell(i, 8, client)
        inv.cell(i, 10, invoice)
        inv.cell(i, 19, status)
        inv.cell(i, 34, "SYNTHETIC_ORIGINAL_AH")
    payment = book.create_sheet("PAYMNENT")
    payment["A1"] = "Description"
    payment["H1"] = "Debit"
    payment["I1"] = "Credit"
    payment["J1"] = "Balance"
    payment["K1"] = "Record For Me"
    payment["H2"] = 900
    payment["I2"] = 123.45
    payment["I3"] = -10
    return book


def master_workbook():
    book = Workbook()
    sheet = book.active
    sheet.title = "Clean Branch Master"
    sheet["A1"] = "Search Aliases"
    sheet["B1"] = "Official Branch Name"
    sheet["C1"] = "Matched Branch Name(s) from Arranged Data"
    sheet["D1"] = "SOL ID"
    sheet["B2"], sheet["D2"] = "BRANCH ALPHA", "00001"
    sheet["B3"], sheet["D3"] = "BRANCH BETA", "00002"
    sheet["B4"], sheet["D4"] = "BRANCH GAMMA", "00003"
    return book


def scan(source=None, master=None):
    src = workbook_bytes(source or source_workbook())
    m = workbook_bytes(master or master_workbook())
    return shadow_identity_preflight(
        src, m,
        expected_source_sha256=hashlib.sha256(src).hexdigest(),
        expected_master_sha256=hashlib.sha256(m).hexdigest(),
    )


class R16IdentityShadowTests(unittest.TestCase):
    def test_01_clean_exact_sol_and_name_is_only_shadow(self):
        report = scan()
        c = report["invoice_identity_counts"]
        self.assertEqual(c["candidate_exact_sol_and_official_name_only"], 1)
        self.assertEqual(c["protected_paid_marker_s_nonblank"], 1)
        self.assertEqual(c["candidate_unverified_client_name"], 1)
        self.assertEqual(c["candidate_sol_not_in_verified_master"], 1)
        self.assertEqual(c["duplicate_invoice_rows_quarantined"], 2)
        self.assertEqual(report["invoice_duplicate_id_groups"], 1)

    def test_02_immutable_input_bytes_and_hashes(self):
        src = workbook_bytes(source_workbook())
        m = workbook_bytes(master_workbook())
        src_hash, m_hash = hashlib.sha256(src).hexdigest(), hashlib.sha256(m).hexdigest()
        out = shadow_identity_preflight(
            src, m, expected_source_sha256=src_hash, expected_master_sha256=m_hash
        )
        self.assertEqual(hashlib.sha256(src).hexdigest(), src_hash)
        self.assertEqual(hashlib.sha256(m).hexdigest(), m_hash)
        self.assertEqual(out["source_sha256"], src_hash)
        self.assertEqual(out["master_sha256"], m_hash)

    def test_03_missing_source_bytes_refused(self):
        m = workbook_bytes(master_workbook())
        with self.assertRaisesRegex(IdentityGateRefused, "FRESH_FINANCIAL_SOURCE_BYTES_REQUIRED"):
            shadow_identity_preflight(
                b"", m, expected_source_sha256="0" * 64,
                expected_master_sha256=hashlib.sha256(m).hexdigest()
            )

    def test_04_source_manifest_sha_required(self):
        src = workbook_bytes(source_workbook())
        m = workbook_bytes(master_workbook())
        with self.assertRaisesRegex(IdentityGateRefused, "EXPLICIT_SHA256_MANIFEST_REQUIRED"):
            shadow_identity_preflight(
                src, m, expected_source_sha256="",
                expected_master_sha256=hashlib.sha256(m).hexdigest()
            )

    def test_05_source_hash_mismatch_refused(self):
        src = workbook_bytes(source_workbook())
        m = workbook_bytes(master_workbook())
        with self.assertRaisesRegex(IdentityGateRefused, "SOURCE_SHA256_MISMATCH"):
            shadow_identity_preflight(
                src, m, expected_source_sha256="0"*64,
                expected_master_sha256=hashlib.sha256(m).hexdigest()
            )

    def test_06_master_hash_mismatch_refused(self):
        src = workbook_bytes(source_workbook())
        m = workbook_bytes(master_workbook())
        with self.assertRaisesRegex(IdentityGateRefused, "MASTER_SHA256_MISMATCH"):
            shadow_identity_preflight(
                src, m, expected_source_sha256=hashlib.sha256(src).hexdigest(),
                expected_master_sha256="0"*64
            )

    def test_07_numeric_sol_in_master_is_not_coerced(self):
        m = master_workbook()
        m["Clean Branch Master"]["D2"] = 1
        report = scan(master=m)
        self.assertEqual(report["master_invalid_identity_rows"], 1)
        self.assertEqual(report["invoice_identity_counts"]["candidate_sol_not_in_verified_master"], 2)

    def test_08_numeric_sol_in_invoice_is_not_coerced(self):
        src = source_workbook()
        src["Invoice Details."]["G2"] = 1
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["candidate_missing_or_nontext_sol"], 1)

    def test_09_leading_zero_sol_not_merged(self):
        m = master_workbook()
        sheet = m["Clean Branch Master"]
        sheet["B5"], sheet["D5"] = "BRANCH OTHER", "1"
        report = scan(master=m)
        self.assertEqual(report["master_padded_sol_collision_groups"], 1)
        self.assertEqual(report["invoice_identity_counts"]["candidate_exact_sol_and_official_name_only"], 1)

    def test_10_conflicting_official_names_quarantined(self):
        m = master_workbook()
        sheet = m["Clean Branch Master"]
        sheet["B5"], sheet["D5"] = "DIFFERENT BRANCH", "00001"
        report = scan(master=m)
        self.assertEqual(report["master_ambiguous_sol_keys"], 1)
        self.assertEqual(report["invoice_identity_counts"]["candidate_ambiguous_master_sol"], 1)

    def test_11_nonblank_S_numeric_zero_is_protected(self):
        src = source_workbook()
        src["Invoice Details."]["S2"] = 0
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["protected_paid_marker_s_nonblank"], 2)
        self.assertEqual(report["invoice_identity_counts"].get("candidate_exact_sol_and_official_name_only",0), 0)

    def test_12_source_client_mismatch_on_exact_sol_is_review_only(self):
        src = source_workbook()
        src["Invoice Details."]["H2"] = "OTHER BRANCH"
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["candidate_client_name_mismatch_review"], 1)

    def test_13_duplicate_invoice_group_quarantine_includes_source_rows(self):
        src = source_workbook()
        src["Invoice Details."]["J2"] = "MXP10005"
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["duplicate_invoice_rows_quarantined"], 3)
        self.assertEqual(report["invoice_duplicate_id_groups"], 1)

    def test_14_missing_invoice_number_is_not_eligible_identity(self):
        src = source_workbook()
        src["Invoice Details."]["J2"] = ""
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["candidate_identity_on_hold"], 3)

    def test_15_invalid_invoice_header_contract_refused(self):
        src = source_workbook()
        src["Invoice Details."]["J1"] = "Wrong"
        with self.assertRaisesRegex(IdentityGateRefused, "INVOICE_G_H_J_M_HEADER_CONTRACT_MISMATCH"):
            scan(source=src)

    def test_16_missing_master_sheet_refused(self):
        m = master_workbook()
        m["Clean Branch Master"].title = "Not the Master"
        with self.assertRaisesRegex(IdentityGateRefused, "MASTER_REQUIRED_SHEET_MISSING"):
            scan(master=m)

    def test_17_missing_master_required_column_refused(self):
        m = master_workbook()
        m["Clean Branch Master"]["D1"] = "Wrong SOL"
        with self.assertRaisesRegex(IdentityGateRefused, "MASTER_REQUIRED_HEADERS_MISSING"):
            scan(master=m)

    def test_18_duplicate_master_required_header_refused(self):
        m = master_workbook()
        m["Clean Branch Master"]["E1"] = "SOL ID"
        with self.assertRaisesRegex(IdentityGateRefused, "MASTER_REQUIRED_HEADER_DUPLICATE"):
            scan(master=m)

    def test_19_three_column_payment_evidence_does_not_count_as_bank_source(self):
        src = Workbook()
        src.active.title = "PAYMENT EVIDENCE"
        src.active.append(["Description", "SOL ID", "Credit Amount"])
        with self.assertRaisesRegex(IdentityGateRefused, "R15_WRONG_INPUT"):
            scan(source=src)

    def test_20_negative_credit_remains_review_and_unallocated(self):
        report = scan()
        self.assertEqual(report["payment_credit_evidence_counts"]["negative_review"], 1)
        self.assertEqual(report["financial_payment_allocations"], 0)

    def test_21_public_output_never_exposes_client_names_or_invoice_numbers(self):
        report = scan()
        output = repr(report)
        for forbidden in ("BRANCH ALPHA", "BRANCH BETA", "MXP10001", "123.45"):
            self.assertNotIn(forbidden, output)

    def test_22_not_a_master_authority_or_financial_certification(self):
        report = scan()
        for key in (
            "historical_master_authority_verified",
            "source_fresh_upload_attestation_verified",
            "v251_allocation_engine_connected",
            "financial_database_connected",
            "release_authorized",
        ):
            self.assertFalse(report[key])
        self.assertTrue(report["financial_apply_locked"])
        self.assertEqual(report["invoice_status_updates"], 0)
        self.assertFalse(report["master_aliases_used"])

    def test_23_formula_invoice_number_is_held_not_a_reference(self):
        src = source_workbook()
        src["Invoice Details."]["J2"] = "=1+1"
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["invoice_no_missing_or_nontext"], 1)
        self.assertEqual(report["invoice_identity_counts"]["candidate_identity_on_hold"], 3)

    def test_24_formula_client_is_not_accepted_as_verified(self):
        src = source_workbook()
        src["Invoice Details."]["H2"] = "=\"BRANCH ALPHA\""
        report = scan(source=src)
        self.assertEqual(report["invoice_identity_counts"]["candidate_unverified_client_name"], 2)

    def test_25_alias_not_used_for_auto_matching(self):
        m = master_workbook()
        m["Clean Branch Master"]["A2"] = "DIFFERENT ALIAS"
        src = source_workbook()
        src["Invoice Details."]["H2"] = "DIFFERENT ALIAS"
        report = scan(master=m, source=src)
        self.assertEqual(report["invoice_identity_counts"]["candidate_client_name_mismatch_review"], 1)
        self.assertFalse(report["master_aliases_used"])


    def test_26_approved_history_invoice_is_in_J_and_sgst_in_M(self):
        source = source_workbook()
        invoice_sheet = source["Invoice Details."]
        self.assertEqual(invoice_sheet["J1"].value, "Invoice No")
        self.assertEqual(invoice_sheet["M1"].value, "SGST")
        self.assertEqual(invoice_sheet["J2"].value, "MXP10001")
        self.assertIsNone(invoice_sheet["M2"].value)  # source SGST is untouched by identity tests
        report = scan(source=source)
        self.assertEqual(report["invoice_identity_counts"]["candidate_exact_sol_and_official_name_only"], 1)

    def test_27_original_monetary_SGST_column_must_not_be_invoice_number(self):
        source = source_workbook()
        invoice_sheet = source["Invoice Details."]
        invoice_sheet["M2"] = 999.99
        report = scan(source=source)
        self.assertEqual(report["invoice_duplicate_id_groups"], 1)
        self.assertEqual(report["invoice_identity_counts"]["candidate_exact_sol_and_official_name_only"], 1)
        self.assertEqual(invoice_sheet["M2"].value, 999.99)

    def test_28_wrong_sgst_header_M_refused_even_if_J_correct(self):
        source = source_workbook()
        source["Invoice Details."]["M1"] = "Invoice No"
        with self.assertRaisesRegex(IdentityGateRefused, "INVOICE_G_H_J_M_HEADER_CONTRACT_MISMATCH"):
            scan(source=source)

    def test_29_protected_S_independent_of_payment_date_interpretation(self):
        source = source_workbook()
        source["Invoice Details."]["S2"] = "2026-01-15"
        report = scan(source=source)
        self.assertEqual(report["invoice_identity_counts"]["protected_paid_marker_s_nonblank"], 2)
        self.assertEqual(report["invoice_identity_counts"].get(
            "candidate_exact_sol_and_official_name_only", 0), 0)



if __name__ == "__main__":
    unittest.main()
