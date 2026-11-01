"""Synthetic, pure unit tests for import receipt completeness (no Firestore access)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))

from import_receipt_audit import audit_import_receipts


RID1 = "a" * 32
RID2 = "b" * 32


def receipt(rid, *, status="PREVIEW_READY", total=3, ready=2,
            added=0, rejected=1, processed=1, finance=False):
    return (rid, {
        "receipt": rid, "status": status, "total_count": total,
        "ready_count": ready, "added_count": added,
        "rejected_count": rejected, "processed_count": processed,
        "finance_processed": finance,
    })


class ImportReceiptAuditTests(unittest.TestCase):
    def test_empty_ledger_matches_zero_import_snapshot(self):
        result = audit_import_receipts([], [], {"completed_import_rows": 0})
        self.assertEqual(result["result"], "PASS_ZERO_IMPORTS")
        self.assertEqual(result["scope"], "IMPORT_LEDGER_ONLY")
        self.assertEqual(result["baseline_snapshot_freshness"], "NOT_CERTIFIED")
        self.assertFalse(result["database_writes"])

    def test_preview_receipt_without_committed_imports_is_safe(self):
        result = audit_import_receipts(
            [receipt(RID1)], [], {"completed_import_rows": 0})
        self.assertEqual(result["result"], "PASS_ZERO_IMPORTS")
        self.assertEqual(result["receipt_status_counts"], {"PREVIEW_READY": 1})

    def test_completed_receipt_with_only_rejections_is_safe(self):
        result = audit_import_receipts(
            [receipt(RID1, status="COMPLETED", total=2, ready=0,
                     added=0, rejected=2, processed=2)],
            [], {"completed_import_rows": 0})
        self.assertEqual(result["result"], "PASS_ZERO_IMPORTS")

    def test_applied_rows_require_identity_hash_even_if_counts_match(self):
        result = audit_import_receipts(
            [receipt(RID1, status="COMPLETED", total=1, ready=1,
                     added=1, rejected=0, processed=1)],
            [{"import_receipt": RID1}], {"completed_import_rows": 1})
        self.assertEqual(result["result"], "REVIEW_REQUIRED")
        self.assertIn("NONZERO_IMPORT_ROWSET_IDENTITY_NOT_CERTIFIED",
                      result["blockers"])

    def test_nonfinal_applied_rows_never_pass(self):
        result = audit_import_receipts(
            [receipt(RID1, status="PREVIEW_READY", total=2, ready=2,
                     added=1, rejected=0, processed=1)],
            [], {"completed_import_rows": 0})
        self.assertIn("NONAPPLIED_RECEIPT_HAS_COMMITTED_ROWS",
                      result["blockers"])

    def test_in_progress_receipt_requires_review(self):
        result = audit_import_receipts(
            [receipt(RID1, status="APPLYING", total=2, ready=2,
                     added=0, rejected=0, processed=0)],
            [], {"completed_import_rows": 0})
        self.assertIn("IMPORT_APPLY_IN_PROGRESS", result["blockers"])

    def test_orphaned_completed_rows_never_pass(self):
        result = audit_import_receipts(
            [], [{"import_receipt": RID1}], {"completed_import_rows": 1})
        self.assertIn("ORPHANED_OR_NONFINAL_IMPORTED_ROW",
                      result["blockers"])

    def test_completed_receipt_missing_a_row_never_pass(self):
        result = audit_import_receipts(
            [receipt(RID1, status="COMPLETED", total=2, ready=2,
                     added=2, rejected=0, processed=2)],
            [{"import_receipt": RID1}], {"completed_import_rows": 1})
        self.assertIn("COMPLETED_RECEIPT_ROW_COUNT_MISMATCH",
                      result["blockers"])

    def test_stale_report_count_never_pass(self):
        result = audit_import_receipts(
            [], [], {"completed_import_rows": 1})
        self.assertIn("REPORT_SNAPSHOT_IMPORT_COUNT_STALE",
                      result["blockers"])

    def test_unknown_receipt_state_never_pass(self):
        result = audit_import_receipts(
            [receipt(RID1, status="UNKNOWN")], [],
            {"completed_import_rows": 0})
        self.assertIn("UNKNOWN_RECEIPT_STATUS", result["blockers"])

    def test_duplicate_receipts_never_pass(self):
        r = receipt(RID1)
        result = audit_import_receipts(
            [r, r], [], {"completed_import_rows": 0})
        self.assertIn("INVALID_OR_DUPLICATED_RECEIPT", result["blockers"])

    def test_unknown_or_boolean_counts_do_not_pass(self):
        for value in (None, True, -1, "0"):
            with self.subTest(value=value):
                r = receipt(RID1)
                r[1]["added_count"] = value
                result = audit_import_receipts(
                    [r], [], {"completed_import_rows": 0})
                self.assertIn("INVALID_RECEIPT_COUNTERS",
                              result["blockers"])

    def test_invalid_manifest_count_never_pass(self):
        for manifest in ({}, {"completed_import_rows": True},
                         {"completed_import_rows": -1}):
            with self.subTest(manifest=manifest):
                result = audit_import_receipts([], [], manifest)
                self.assertIn("MISSING_REPORT_IMPORT_COUNT",
                              result["blockers"])

    def test_unknown_receipt_finance_processed_rejected(self):
        result = audit_import_receipts(
            [receipt(RID2, finance=True)], [],
            {"completed_import_rows": 0})
        self.assertIn("INCONSISTENT_RECEIPT_COUNTERS", result["blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
