"""Synthetic negative release tests; no real bank data or network access."""
import csv
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from owner_candidate_policy_gate import audit_owner_policy, POLICY

ORIGINAL = [
    "Bank Source Row (PAYMNENT)",
    "Bank Credit Column I (Original)",
    "Candidate Category (SCREEN ONLY)",
] + [f"Original source field {i}" for i in range(29)]
EXTRA = [
    "Owner Review Business Rule ID",
    "Owner Review Policy Approval",
    "Owner Approved Conditional Treatment",
    "Required Evidence Before Per-Transaction OK",
    "Owner Review Comment (verbatim)",
    "Source Review CSV SHA-256",
    "Owner Business Rule Review Date (IST)",
    "Independent Per-Row Payment Evidence",
    "New Owner-Approved Financial Allocation",
    "Financial Release Permission",
    "Reserved Policy Audit Field",
]


def fixture():
    left = []
    right = []
    for i, (category, rule) in enumerate(POLICY.items(), 2):
        row = {k: "" for k in ORIGINAL}
        row.update({
            ORIGINAL[0]: str(i),
            ORIGINAL[1]: "25.40",
            ORIGINAL[2]: category,
            "Original source field 0": "000123",
        })
        left.append(row)
        r = dict(row)
        r.update({
            "Owner Review Business Rule ID": rule,
            "Owner Review Policy Approval": "APPROVED_BY_ACCOUNT_HOLDER_POLICY_ONLY",
            "Owner Approved Conditional Treatment": "Review conditional match method",
            "Required Evidence Before Per-Transaction OK": "Invoice/credit/date/source",
            "Owner Review Comment (verbatim)": "Owner instruction",
            "Source Review CSV SHA-256": "synthetic",
            "Owner Business Rule Review Date (IST)": "2026-11-06",
            "Independent Per-Row Payment Evidence": "NOT_VERIFIED_IN_OWNER_REVIEW_CSV",
            "New Owner-Approved Financial Allocation": "NONE_CONFIRMED_IN_THIS_REVIEW",
            "Financial Release Permission": "NOT_GRANTED_BY_POLICY_REVIEW",
            "Reserved Policy Audit Field": "",
            "New Allocation Approved": "NO",
            "Provisional Model Decision (NO WRITE)": "UNRESOLVED_REVIEW_REQUIRED",
        })
        # The two model status fields are canonical source fields in the real contract.
        left[-1]["New Allocation Approved"] = "NO"
        left[-1]["Provisional Model Decision (NO WRITE)"] = "UNRESOLVED_REVIEW_REQUIRED"
        right.append(r)
    return left, right


# Rebuild the synthetic 32-col canonical header with its mandatory two source model fields.
ORIGINAL[-2:] = ["New Allocation Approved", "Provisional Model Decision (NO WRITE)"]


class OwnerCandidatePolicyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_file = pathlib.Path(self.temp.name) / "original.csv"
        self.reviewed_file = pathlib.Path(self.temp.name) / "reviewed.csv"
        self.original, self.reviewed = fixture()

    def tearDown(self):
        self.temp.cleanup()

    def run_gate(self):
        with self.original_file.open("w", newline="", encoding="utf-8") as file:
            w = csv.DictWriter(file, fieldnames=ORIGINAL)
            w.writeheader()
            w.writerows(self.original)
        with self.reviewed_file.open("w", newline="", encoding="utf-8") as file:
            w = csv.DictWriter(file, fieldnames=ORIGINAL + EXTRA)
            w.writeheader()
            w.writerows(self.reviewed)
        return audit_owner_policy(
            str(self.original_file), str(self.reviewed_file),
            expected_counts={k: 1 for k in POLICY},
        )

    def test_01_owner_methods_can_pass_without_external_signoff(self):
        result = self.run_gate()
        self.assertEqual(result["owner_method_approval"], "PASS_3_OF_3")
        self.assertEqual(result["rows_verified"], 3)

    def test_02_production_remains_blocked_after_owner_policy_pass(self):
        result = self.run_gate()
        self.assertEqual(result["production_release"], "BLOCKED")
        self.assertEqual(result["individual_payment_allocations"], 0)

    def test_03_all_original_bank_fields_immutable(self):
        self.reviewed[0]["Original source field 0"] = "000124"
        with self.assertRaisesRegex(ValueError, "altered"):
            self.run_gate()

    def test_04_no_approval_of_payments_by_category(self):
        self.original[0]["New Allocation Approved"] = "YES"
        self.reviewed[0]["New Allocation Approved"] = "YES"
        with self.assertRaisesRegex(ValueError, "Unapproved transaction"):
            self.run_gate()

    def test_05_no_lifting_finance_release_by_csv(self):
        self.reviewed[0]["Financial Release Permission"] = "GRANTED"
        with self.assertRaisesRegex(ValueError, "Unapproved transaction"):
            self.run_gate()

    def test_06_unknown_candidate_category_denied(self):
        self.original[0][ORIGINAL[2]] = "UNKNOWN"
        self.reviewed[0][ORIGINAL[2]] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "Unknown candidate"):
            self.run_gate()

    def test_07_duplicate_bank_row_denied(self):
        self.original[1][ORIGINAL[0]] = self.original[0][ORIGINAL[0]]
        self.reviewed[1][ORIGINAL[0]] = self.reviewed[0][ORIGINAL[0]]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_gate()

    def test_08_mismatched_owner_rule_denied(self):
        self.reviewed[0]["Owner Review Business Rule ID"] = "OWNER-RULE-03"
        with self.assertRaisesRegex(ValueError, "Wrong approved"):
            self.run_gate()

    def test_09_insufficient_invoice_evidence_denied(self):
        self.reviewed[1]["Required Evidence Before Per-Transaction OK"] = ""
        with self.assertRaisesRegex(ValueError, "Missing transaction"):
            self.run_gate()

    def test_10_row_count_drift_denied(self):
        self.reviewed.pop()
        with self.assertRaisesRegex(ValueError, "row-count mismatch"):
            self.run_gate()

    def test_11_negative_credit_denied(self):
        self.original[0][ORIGINAL[1]] = "-1"
        self.reviewed[0][ORIGINAL[1]] = "-1"
        with self.assertRaisesRegex(ValueError, "Invalid positive"):
            self.run_gate()

    def test_12_wrong_expected_counts_denied(self):
        self.assertEqual(self.run_gate()["rows_verified"], 3)
        with self.assertRaisesRegex(ValueError, "Changed candidate"):
            audit_owner_policy(
                str(self.original_file), str(self.reviewed_file),
                expected_counts={"SINGLE_POTENTIAL_SAME_SOL_TDS": 10},
            )


if __name__ == "__main__":
    unittest.main()
