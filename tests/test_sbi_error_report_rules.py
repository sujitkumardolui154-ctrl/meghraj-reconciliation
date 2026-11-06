"""Issue #76 synthetic regression: no network, cloud credentials or financial rows."""
import copy
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend_source"))

from invoice_source_schema import HEADERS_53
from credit_note_53_adapter import REPORT_HEADERS, project_credit_notes
from error_report_rules import audit_error_report, render_error_report_csv, summarize, RULES

HASH = "a" * 64


def fixture(invoice="INV001"):
    row = [""] * 53
    row[6] = "0001"
    row[8] = "0001"
    row[10] = "0001"
    row[12] = invoice
    row[13:17] = ["100", "9", "9", "118"]
    row[17] = "1"
    row[20] = "117"
    row[37] = "OK"
    return row


def check(rows, **options):
    return audit_error_report(HEADERS_53, rows, source_sha256=HASH, **options)


def rule_set(items):
    return {x["Error Code"] for x in items}


def invoice_flags(items, rule):
    return [x for x in items if x["Error Code"] == rule and x["Source Row"]]


class ErrorReportRules(unittest.TestCase):
    def test_01_approved_schema_locked(self):
        self.assertEqual(len(HEADERS_53), 53)
        self.assertEqual(HEADERS_53[0], HEADERS_53[7])
        self.assertEqual(HEADERS_53[6], HEADERS_53[10])
        with self.assertRaises(ValueError):
            audit_error_report(HEADERS_53[::-1], [fixture()], source_sha256=HASH)

    def test_02_dataset_gates_fail_closed(self):
        flags = check([fixture()])
        for code in ("ERR-08_PAYMENT_EVIDENCE_MISSING",
                     "ERR-10_MASTER_REPORT_PARITY", "ERR-11_CREDIT_NOTE_PARITY",
                     "ERR-12_BACKUP_ROLLBACK"):
            self.assertIn(code, rule_set(flags))
        self.assertEqual(len([f for f in flags if not f["Source Row"]]), 4)

    def test_03_gross_amount_and_signed_difference(self):
        row = fixture()
        row[16] = "118.12"
        findings = invoice_flags(check([row]), "ERR-01_GROSS_MISMATCH")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["Difference"], "0.12")
        row[16] = "118.01"
        self.assertFalse(invoice_flags(check([row]), "ERR-01_GROSS_MISMATCH"))

    def test_04_invalid_financial_cells(self):
        row = fixture()
        row[15] = "#VALUE!"
        flags = invoice_flags(check([row]), "ERR-02_INVALID_FINANCIAL_VALUE")
        self.assertEqual(len(flags), 1)
        self.assertFalse(invoice_flags(check([row]), "ERR-01_GROSS_MISMATCH"))

    def test_05_duplicate_real_invoice_separate_from_NA(self):
        flags = check([fixture("INV1"), fixture("INV1"),
                       fixture("NA"), fixture("NA"), fixture("")])
        self.assertEqual(len(invoice_flags(flags, "ERR-03_DUPLICATE_INVOICE")), 2)
        self.assertEqual(len(invoice_flags(flags, "ERR-04_INVALID_INVOICE_NUMBER")), 3)

    def test_06_branch_and_sol_disagreement(self):
        row = fixture()
        row[10] = "0002"
        row[8] = "0003"
        codes = rule_set(check([row]))
        self.assertIn("ERR-05_BRANCH_CODE_CONFLICT", codes)
        self.assertIn("ERR-06_SOL_MISMATCH", codes)

    def test_07_missing_model_sol(self):
        row = fixture()
        row[8] = ""
        codes = rule_set(check([row]))
        self.assertIn("ERR-07_MISSING_MODEL_SOL", codes)
        self.assertNotIn("ERR-06_SOL_MISMATCH", codes)

    def test_08_missing_bank_ledger_is_dataset_not_10000_accusations(self):
        rows = [fixture("INV1"), fixture("INV2")]
        dataset = check(rows, report_category="ok")
        self.assertEqual(len([f for f in dataset if f["Error Code"].startswith("ERR-08")]), 1)
        per_invoice = check(rows, report_category="ok", bank_evidence={"INV1": ["ref"]})
        self.assertEqual(len(invoice_flags(per_invoice, "ERR-08_PAYMENT_EVIDENCE_MISSING")), 1)

    def test_09_status_conflicts(self):
        row = fixture()
        row[37] = "SKIPPED — EXISTING PAYMENT"
        self.assertIn("ERR-09_STATUS_EVIDENCE_CONFLICT",
                      rule_set(check([row], report_category="ok")))
        self.assertNotIn("ERR-09_STATUS_EVIDENCE_CONFLICT",
                         rule_set(check([row], report_category="unpaid")))

    def test_10_approved_master_compare(self):
        old = fixture()
        changed = fixture()
        changed[13] = "200"
        evidence = {"headers": HEADERS_53, "rows": [old]}
        self.assertTrue(invoice_flags(check([changed], approved_master=evidence),
                                      "ERR-10_MASTER_REPORT_PARITY"))
        self.assertFalse(invoice_flags(check([old], approved_master=evidence),
                                       "ERR-10_MASTER_REPORT_PARITY"))

    def test_11_credit_note_projection_check(self):
        row = fixture()
        projected, _ = project_credit_notes(HEADERS_53, [row])
        valid = {"headers": REPORT_HEADERS, "rows": [projected[0]]}
        self.assertNotIn("ERR-11_CREDIT_NOTE_PARITY", rule_set(check([row], credit_note_report=valid)))
        incorrect = copy.deepcopy(valid)
        incorrect["rows"][0]["CGST"] = "10"
        self.assertIn("ERR-11_CREDIT_NOTE_PARITY",
                      rule_set(check([row], credit_note_report=incorrect)))

    def test_12_isolated_synthetic_backup_fingerprint(self):
        blob = b"synthetic-backup-data"
        expected = hashlib.sha256(blob).hexdigest()
        good = {"snapshot_bytes": blob, "restored_bytes": blob,
                "snapshot_sha256": expected, "isolated": True}
        self.assertNotIn("ERR-12_BACKUP_ROLLBACK", rule_set(check([fixture()], backup_proof=good)))
        bad = dict(good, restored_bytes=b"corrupt")
        self.assertIn("ERR-12_BACKUP_ROLLBACK", rule_set(check([fixture()], backup_proof=bad)))

    def test_13_source_untouched_and_counts(self):
        row = fixture()
        saved = copy.deepcopy(row)
        flags = check([row])
        self.assertEqual(row, saved)
        stats = summarize(flags)
        self.assertEqual(stats["findings"], len(flags))
        self.assertEqual(stats["unresolved"], len(flags))
        self.assertTrue(all(f["Review Decision"] == "PENDING_REVIEW" for f in flags))
        self.assertTrue(set(f["Error Code"] for f in flags).issubset(RULES))

    def test_14_csv_formula_injection_defense(self):
        row = fixture("=1+2")
        output = render_error_report_csv(check([row], report_category="ok"))
        self.assertIn("'=1+2", output)
        self.assertIn("Error Code", output)

    def test_15_invalid_source_shapes_rejected(self):
        with self.assertRaises(ValueError):
            check([fixture()[:52]])
        with self.assertRaises(ValueError):
            audit_error_report(HEADERS_53, [fixture()], source_sha256="not-hash")
        with self.assertRaises(ValueError):
            check([{"Invoice No": "INV001"}])


if __name__ == "__main__":
    unittest.main()
