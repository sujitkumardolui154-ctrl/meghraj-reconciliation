"""Offline QA, no AWS, Firestore, network, production or financial writes."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
from credit_note_validation import (
    marker_classification, is_credit_note_marker, audit_credit_note_rows
)
from credit_note_import_preview import (
    build_credit_note_import_preview, summarize_invoice_upload_credit_notes
)
from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53, row_layout


def item(invoice="MXP1001", cn="MXPCN1001", marker="CREDIT NOTE", **kw):
    data = {"Invoice No": invoice, "Credit Note No": cn,
            "Payment Received (If With GST or Excluding GST)": marker}
    data.update(kw)
    return data


class CreditNotePreviewTests(unittest.TestCase):
    def test_plain_and_dated(self):
        for marker in ("CREDIT NOTE", "Credit Note @ 30/11/2024",
                       "credit note @ April 2026", "Credit Note 30 12 2024"):
            with self.subTest(marker=marker):
                self.assertTrue(is_credit_note_marker(marker))

    def test_bad_date_and_spelling_are_review(self):
        for marker in ("CREDIT NOTE @ 31/02/2024", "CREDITE NOTE",
                       "CREDIT NOTE @", "Credit Note signed"):
            with self.subTest(marker=marker):
                self.assertEqual(marker_classification(marker), "REVIEW")

    def test_duplicates_mark_both_rows_error(self):
        r = audit_credit_note_rows([item(), item(cn="MXPCN1002")])
        self.assertEqual(r["summary"]["error_rows"], 2)
        self.assertEqual(r["summary"]["error_flags"]["DUPLICATE_INVOICE_NUMBER"], 2)

    def test_duplicate_cn_number(self):
        r = audit_credit_note_rows([item(), item(invoice="MXP1002")])
        self.assertEqual(r["summary"]["error_flags"]["DUPLICATE_CREDIT_NOTE_NUMBER"], 2)

    def test_non_mxp_cn_number_error(self):
        r = audit_credit_note_rows([item(cn="CN123")])
        self.assertEqual(r["summary"]["error_flags"]["INVALID_CREDIT_NOTE_NO_NON_MXP"], 1)

    def test_non_mxp_invoice_reference_error(self):
        r = audit_credit_note_rows([item(invoice="XYZ100")])
        self.assertEqual(r["summary"]["error_flags"]["INVALID_INVOICE_NO_NON_MXP"], 1)

    def test_mxp_bare_invalid(self):
        r = audit_credit_note_rows([item(cn="MXP")])
        self.assertEqual(r["summary"]["error_rows"], 1)

    def test_cross_upload_cn_registry(self):
        r = audit_credit_note_rows([item()], existing_credit_note_numbers={"mxpcn1001"})
        self.assertEqual(r["summary"]["error_flags"]["CREDIT_NOTE_NUMBER_ALREADY_EXISTS"], 1)

    def test_existing_invoice_reference_expected(self):
        r = audit_credit_note_rows([item()], approved_invoice_numbers={"MXP1001"},
                                   existing_credit_note_numbers=set())
        self.assertEqual(r["summary"]["error_rows"], 0)

    def test_unknown_invoice_reference_error(self):
        r = audit_credit_note_rows([item()], approved_invoice_numbers={"MXP9999"})
        self.assertEqual(r["summary"]["error_flags"]["INVOICE_REFERENCE_NOT_IN_APPROVED_REGISTER"], 1)

    def test_registry_missing_not_pass(self):
        r = audit_credit_note_rows([item()])
        self.assertEqual(r["summary"]["approved_registers"], "NOT_VERIFIED")

    def test_missing_cn_column_blocked(self):
        with self.assertRaisesRegex(ValueError, "Dedicated Credit Note No"):
            audit_credit_note_rows([{"Invoice No": "MXP1001"}])

    def test_replacement_duplicates_and_non_mxp(self):
        r = audit_credit_note_rows([
            item("MXP1001", "MXPCN1001", **{"New Invoice Agansit of Credit Note": "CN789"}),
            item("MXP1002", "MXPCN1002", **{"New Invoice Agansit of Credit Note": "CN789"}),
        ])
        self.assertEqual(r["summary"]["error_flags"]["INVALID_REPLACEMENT_INVOICE_NO_NON_MXP"], 2)
        self.assertEqual(r["summary"]["error_flags"]["DUPLICATE_REPLACEMENT_INVOICE_NO"], 2)

    def test_source_unmodified(self):
        data = [item()]
        old = copy.deepcopy(data)
        audit_credit_note_rows(data)
        self.assertEqual(old, data)

    def test_import_never_approved(self):
        r = build_credit_note_import_preview([item()], approved_credit_note_numbers=set(),
                                             approved_invoice_numbers={"MXP1001"})
        self.assertFalse(r["import_ready"])
        self.assertFalse(r["database_changed"])
        self.assertFalse(r["summary"]["production_approval"])

    def test_schema_positions_and_annotation(self):
        for headers in (HEADERS_34, HEADERS_35, HEADERS_53):
            with self.subTest(width=len(headers)):
                row = {"original_headers": list(headers), "original_values": [""] * len(headers)}
                _, _, payment_idx, _, _ = row_layout(row)
                row["original_values"][payment_idx] = "CREDIT NOTE @ 30/11/2024"
                result = summarize_invoice_upload_credit_notes([row])
                self.assertEqual(result["normal_or_dated_credit_note_count"], 1)
                self.assertFalse(result["credit_note_import_ready"])

    def test_ambiguous_field_alias_fails_closed(self):
        data = item()
        data["Credit Note Number"] = "MXPCN2000"
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            audit_credit_note_rows([data])

    def test_no_fixed_historical_row_limit(self):
        records = [item("MXP" + str(i), "MXPCN" + str(i)) for i in range(1000, 1050)]
        result = audit_credit_note_rows(records)
        self.assertEqual(result["summary"]["source_rows"], 50)
        self.assertEqual(result["summary"]["error_rows"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
