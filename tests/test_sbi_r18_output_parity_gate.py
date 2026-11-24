"""R18 tests: synthetic-only source attestation and immutable Excel model parity."""
import hashlib
import io
import sys
import unittest
from pathlib import Path
from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ci"))
from sbi_r18_output_parity_gate import (
    R18GateError, audit_candidate_source, verify_xlsx_output_structure,
    PAYMENT_MODEL, INVOICE_MODEL,
)


def dump(workbook):
    b = io.BytesIO()
    workbook.save(b)
    return b.getvalue()


def make_source():
    w = Workbook()
    p = w.active
    p.title = "PAYMNENT"
    i = w.create_sheet("Invoice Details.")
    other = w.create_sheet("AUXILIARY ORIGINAL")
    p["A1"] = "Description"
    p["H1"], p["I1"], p["J1"], p["K1"] = "Debit", "Credit", "Balance", "Record For Me"
    p["H2"], p["I2"], p["J2"] = 1000, 118, 900
    p["I3"] = 116.82
    p["I4"] = -10
    p["K2"] = "ORIGINAL K REMARK"
    p["L2"] = "ORIGINAL PROTECTED L VALUE"
    p["F2"] = "001505"
    p["A2"] = "SYNTHETIC SOURCE"
    p["J3"] = "=SUM(I2:I3)"
    p["I3"].number_format = '#,##0.00'
    for col in range(1, 35):
        i.cell(1, col, "SOURCE_" + str(col))
    i["G1"], i["H1"], i["M1"] = "Branch Code", "Client Name", "Invoice No"
    i["G2"], i["H2"], i["M2"] = "001505", "SYNTHETIC BANK", "SYN-MXP-001"
    i["AH2"] = "=SUM(N2:P2)"
    i["AH2"].number_format = '#,##0.000'
    i["S3"] = 0
    i["AH3"] = "ORIGINAL AH"
    other["A1"] = "AUXILIARY"
    other["A2"] = "=1+2"
    other["B2"] = "UNCHANGED"
    return w


def build_output(src):
    w = load_workbook(io.BytesIO(src))
    p = w["PAYMNENT"]
    i = w["Invoice Details."]
    for idx, name in enumerate(PAYMENT_MODEL, start=13):
        p.cell(1, idx, name)
    for idx, name in enumerate(INVOICE_MODEL, start=35):
        i.cell(1, idx, name)
    p["M2"], p["M3"], p["M4"] = "SUSPENSE", "SUSPENSE", "SUSPENSE"
    p["N2"] = "SYNTHETIC REVIEW ONLY"
    p["O2"] = "SYN-MXP-001"
    i["AI2"] = "001505"
    i["AJ2"] = "SYNTHETIC BANK"
    return w


def check(src=None, output=None):
    src = src if src is not None else dump(make_source())
    output = output if output is not None else dump(build_output(src))
    return verify_xlsx_output_structure(
        src, output, expected_source_sha256=hashlib.sha256(src).hexdigest(),
        expected_candidate_sha256=hashlib.sha256(output).hexdigest(),
    )


class R18SourceAttestation(unittest.TestCase):
    def test_01_missing_engine_returns_blocker(self):
        x = audit_candidate_source(None, None)
        self.assertEqual(x["gate"], "BLOCKED_CANDIDATE_SOURCE_OR_MANIFEST_MISSING")
        self.assertFalse(x["master_v251_certified"])

    def test_02_old_review_engine_hash_denied(self):
        old = "72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf"
        with self.assertRaisesRegex(R18GateError, "OLDER_RECOVERED_REVIEW_SOURCE_DENIED"):
            audit_candidate_source(b"synthetic", {"expected_sha256": old})

    def test_03_old_conservative_hash_denied(self):
        old = "6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3"
        with self.assertRaisesRegex(R18GateError, "OLDER_RECOVERED_REVIEW_SOURCE_DENIED"):
            audit_candidate_source(b"synthetic", {"expected_sha256": old})

    def test_04_expected_sha_required(self):
        with self.assertRaisesRegex(R18GateError, "ENGINE_SOURCE_EXPECTED_SHA256_REQUIRED"):
            audit_candidate_source(b"synthetic", {"claimed_master_version": "v2.51"})

    def test_05_mismatch_refused(self):
        with self.assertRaisesRegex(R18GateError, "ENGINE_SOURCE_SHA256_MISMATCH"):
            audit_candidate_source(b"synthetic", {"expected_sha256": "0"*64})

    def test_06_version_pair_required(self):
        b = b"pure synthetic candidate source"
        with self.assertRaisesRegex(R18GateError, "CANDIDATE_VERSION_NOT_V251_V239"):
            audit_candidate_source(b, {
                "expected_sha256": hashlib.sha256(b).hexdigest(),
                "claimed_master_version": "v2.22", "claimed_matrix_version": "v2.10",
            })

    def test_07_claimed_v251_is_never_signed_off(self):
        b = b"pure synthetic candidate source"
        out = audit_candidate_source(b, {
            "expected_sha256": hashlib.sha256(b).hexdigest(),
            "claimed_master_version": "v2.51", "claimed_matrix_version": "v2.39",
        })
        self.assertFalse(out["master_v251_certified"])
        self.assertFalse(out["approved_rulebook_implementation_verified"])
        self.assertFalse(out["candidate_signature_verified"])
        self.assertTrue(out["financial_apply_locked"])

    def test_08_fake_human_approval_fields_not_enough(self):
        b = b"pure synthetic candidate source"
        out = audit_candidate_source(b, {
            "expected_sha256": hashlib.sha256(b).hexdigest(),
            "claimed_master_version": "v2.51", "claimed_matrix_version": "v2.39",
            "approved": True, "qa_signed": True,
        })
        self.assertFalse(out["master_v251_certified"])
        self.assertFalse(out["full_method_coverage_verified"])


class R18StructureParity(unittest.TestCase):
    def test_09_baseline_synthetic_structure_pass(self):
        r = check()
        self.assertEqual(r["stage"], "R18_V218_XLSX_STRUCTURE_ONLY")
        self.assertTrue(r["original_cells_formulas_number_formats_preserved"])
        self.assertEqual(r["other_original_tabs_preserved"], 1)
        self.assertEqual(r["payment_status_counts_structure_only"], {"SUSPENSE":2})
        self.assertFalse(r["model_money_parity_certified"])

    def test_10_preserves_source_bytes(self):
        src = dump(make_source())
        before = hashlib.sha256(src).hexdigest()
        check(src)
        self.assertEqual(hashlib.sha256(src).hexdigest(), before)

    def test_11_bad_source_digest_rejected(self):
        src = dump(make_source());out=dump(build_output(src))
        with self.assertRaisesRegex(R18GateError, "SOURCE_SHA256_MISMATCH"):
            verify_xlsx_output_structure(src,out,expected_source_sha256="0"*64,
                                         expected_candidate_sha256=hashlib.sha256(out).hexdigest())

    def test_12_bad_candidate_digest_rejected(self):
        src = dump(make_source());out=dump(build_output(src))
        with self.assertRaisesRegex(R18GateError, "CANDIDATE_SHA256_MISMATCH"):
            verify_xlsx_output_structure(src,out,expected_source_sha256=hashlib.sha256(src).hexdigest(),
                                         expected_candidate_sha256="0"*64)

    def test_13_bad_payment_M_header(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["M1"]="WRONG"
        with self.assertRaisesRegex(R18GateError,"PAYMENT_M_TO_W_HEADER_MISMATCH"):check(src,dump(out))

    def test_14_bad_payment_W_header(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["W1"]="WRONG"
        with self.assertRaisesRegex(R18GateError,"PAYMENT_M_TO_W_HEADER_MISMATCH"):check(src,dump(out))

    def test_15_bad_invoice_AI_header(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["AI1"]="WRONG"
        with self.assertRaisesRegex(R18GateError,"INVOICE_AI_TO_AM_HEADER_MISMATCH"):check(src,dump(out))

    def test_16_bad_invoice_AM_header(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["AM1"]="WRONG"
        with self.assertRaisesRegex(R18GateError,"INVOICE_AI_TO_AM_HEADER_MISMATCH"):check(src,dump(out))

    def test_17_extra_sheet_blocked(self):
        src=dump(make_source());out=build_output(src);out.create_sheet("OVERVIEW")
        with self.assertRaisesRegex(R18GateError,"SHEET_NAMES_ORDER_OR_COUNT_CHANGED"):check(src,dump(out))

    def test_18_reordered_tabs_blocked(self):
        src=dump(make_source());out=build_output(src);out._sheets=list(reversed(out._sheets))
        with self.assertRaisesRegex(R18GateError,"SHEET_NAMES_ORDER_OR_COUNT_CHANGED"):check(src,dump(out))

    def test_19_changed_original_payment_I_blocked(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["I2"]=119
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_20_changed_original_debit_H_blocked(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["H2"]=0
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_21_changed_protected_L_blocked(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["L2"]="OK"
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_22_changed_invoice_S_blocked(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["S3"]=None
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_23_changed_AH_formula_blocked(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["AH2"]="=SUM(N2:O2)"
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_24_changed_payment_J_formula_blocked(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["J3"]=234.82
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_25_changed_number_format_blocked(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["I3"].number_format="General"
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_26_other_sheet_formula_preserved(self):
        src=dump(make_source());out=build_output(src);out["AUXILIARY ORIGINAL"]["A2"]="=3+4"
        with self.assertRaisesRegex(R18GateError,"PROTECTED_ORIGINAL"):check(src,dump(out))

    def test_27_positive_bank_credit_m_status_not_blank(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["M2"]=None
        with self.assertRaisesRegex(R18GateError,"POSITIVE_PAYMENT_ROW_M_BLANK"):check(src,dump(out))

    def test_28_reject_nonstandard_financial_status(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["M2"]="REVIEW"
        with self.assertRaisesRegex(R18GateError,"PAYMENT_MODEL_M_INVALID_STATUS"):check(src,dump(out))

    def test_29_no_OK_on_negative_bank_credit(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["M4"]="OK"
        with self.assertRaisesRegex(R18GateError,"NONPOSITIVE_OR_UNVERIFIED_CREDIT"):check(src,dump(out))

    def test_30_old_modelled_workbook_cannot_be_fresh_input(self):
        w=make_source();w["PAYMNENT"]["M1"]="Model Reconciliation Status";src=dump(w);out=build_output(src)
        with self.assertRaisesRegex(R18GateError,"SOURCE_ALREADY_HAS_MODEL_COLUMNS"):check(src,dump(out))

    def test_31_extra_payment_X_model_rejected(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["X1"]="EXTRA"
        with self.assertRaisesRegex(R18GateError,"WRONG_V218_MODEL_COLUMN_BOUNDARIES"):check(src,dump(out))

    def test_32_extra_invoice_AN_model_rejected(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["AN1"]="EXTRA"
        with self.assertRaisesRegex(R18GateError,"WRONG_V218_MODEL_COLUMN_BOUNDARIES"):check(src,dump(out))

    def test_33_structural_OK_never_means_finance_approved(self):
        src=dump(make_source());out=build_output(src);out["PAYMNENT"]["M2"]="OK"
        r=check(src,dump(out))
        self.assertEqual(r["payment_status_counts_structure_only"]["OK"],1)
        self.assertFalse(r["model_financial_statuses_certified"])
        self.assertFalse(r["full_v251_engine_connected"])

    def test_34_extra_invoice_rows_refused(self):
        src=dump(make_source());out=build_output(src);out["Invoice Details."]["AN9"]="EXTRA"
        with self.assertRaisesRegex(R18GateError,"WRONG_V218_MODEL_COLUMN_BOUNDARIES"):check(src,dump(out))

    def test_35_missing_original_payment_sheet_refused(self):
        src=dump(make_source());out=build_output(src);out.remove(out["PAYMNENT"])
        with self.assertRaisesRegex(R18GateError,"SHEET_NAMES_ORDER_OR_COUNT_CHANGED"):check(src,dump(out))

    def test_36_wrong_fresh_invoice_shape_refused_by_R15(self):
        w=make_source();w["Invoice Details."].delete_cols(34);src=dump(w);out=dump(build_output(src))
        with self.assertRaisesRegex(R18GateError,"R15_INVOICE_ORIGINAL_A_TO_AH_MISSING"):check(src,out)


if __name__=="__main__":
    unittest.main()
