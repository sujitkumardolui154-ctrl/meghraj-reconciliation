"""Synthetic verification of historic PR129 invoice evidence for credit notes.

The existing 53-column report is a DISCOVERY source only, NOT an approved
financial credit-note source. No Firestore/AWS network access in these tests.
"""
import unittest

from credit_note_historical_evidence import (
    HistoricalInvoiceEvidenceUnavailable, REVIEW_STATUS,
    lookup_historical_evidence, project_historical_evidence,
)
from invoice_source_schema import HEADERS_53


def report(numbers, *, review=(), overrides=None):
    vals = []
    for number in numbers:
        fields = [""] * 53
        fields[4] = "February 2026"
        fields[5] = "2026-03-28"
        fields[6] = "03970"
        fields[7] = "QA SMECCC KOLKATA"
        fields[8] = "03970"
        fields[9] = "QA SMECCC KOLKATA"
        fields[11] = "19AAACS8577K3ZK"
        fields[12] = number
        fields[13] = "1000.00"
        fields[14] = "90.00"
        fields[15] = "90.00"
        fields[16] = "1180.00"
        fields[20] = "0"
        fields[25] = "0.00"
        if overrides:
            for index, value in overrides.items():
                fields[index] = value
        vals.append({
            "invoice_no": number, "values": fields,
            "payment_kind": "unpaid", "balance_review": False,
        })
    return {
        "version": "invoice-selection-v1",
        "dataset": "synthetic-approved-report-sha256",
        "source_kind": "VERIFIED_READ_ONLY_REPORT_SOURCE",
        "financial_writes": False,
        "reconciliation_executed": False,
        "database_updated": False,
        "matches": vals, "review": list(review),
        "requested_count": len(numbers) + len(review),
        "matched_count": len(vals), "review_count": len(review),
    }


class HistoricalCreditReportReadOnlyContract(unittest.TestCase):
    def test_exact_header_contract_is_53_columns(self):
        self.assertEqual(len(HEADERS_53), 53)
        self.assertEqual(HEADERS_53[12], "Invoice No")
        self.assertEqual(HEADERS_53[13], "Taxable Amount")
        self.assertEqual(HEADERS_53[25], "Creit Note Ammount")

    def test_report_match_displays_source_but_never_eligible_to_issue(self):
        number = "MXP98001"
        result = project_historical_evidence([number], report([number]))
        self.assertTrue(result["history_review_only"])
        self.assertFalse(result["credit_note_eligible"])
        item = result["records"][0]
        self.assertEqual(item["status"], REVIEW_STATUS)
        self.assertFalse(item["credit_note_eligible"])
        self.assertEqual(item["invoice_date_source"], "2026-03-28")
        self.assertEqual(item["service_month_source"], "February 2026")
        self.assertEqual(item["taxable_source"], "1000.00")
        self.assertEqual(item["total_source"], "1180.00")
        self.assertEqual(
            item["blocked_because"],
            "HISTORICAL_CREDIT_LEDGER_AND_TAX_FILING_NOT_CERTIFIED",
        )

    def test_conflict_and_duplicate_are_not_silently_accepted(self):
        number = "MXP98002"
        candidate = report([],review=[{
            "invoice_no": number, "reason": "DUPLICATE_DATABASE_INVOICE_MATCH"
        }])
        result = project_historical_evidence([number],candidate)
        self.assertEqual(result["records"][0]["status"],
                         "DUPLICATE_DATABASE_INVOICE_MATCH")
        self.assertFalse(result["records"][0]["credit_note_eligible"])

    def test_unsafe_financial_attestation_denied(self):
        item = report(["MXP98003"])
        item["financial_writes"] = True
        with self.assertRaisesRegex(HistoricalInvoiceEvidenceUnavailable,
                                    "SOURCE_READONLY_ATTESTATION"):
            project_historical_evidence(["MXP98003"],item)

    def test_missing_match_from_contract_denied(self):
        item = report(["MXP98004"])
        item["matched_count"] = 0
        with self.assertRaisesRegex(HistoricalInvoiceEvidenceUnavailable,
                                    "HISTORICAL_LOOKUP_CONTRACT"):
            project_historical_evidence(["MXP98004"],item)

    def test_invalid_total_and_conflicting_sol_flagged(self):
        item = report(["MXP98005"],overrides={8:"03971",16:"1111.00"})
        source = project_historical_evidence(["MXP98005"],item)["records"][0]
        self.assertIn("SOURCE_SOL_ID_NOT_INDEPENDENTLY_VERIFIED",
                      source["source_review_flags"])
        self.assertIn("SOURCE_TAX_TOTAL_CONFLICT",source["source_review_flags"])
        self.assertFalse(source["credit_note_eligible"])

    def test_existing_credit_marker_does_not_mean_available_balance(self):
        item = report(["MXP98006"],overrides={25:"200.00"})
        source = project_historical_evidence(["MXP98006"],item)["records"][0]
        self.assertIn("HISTORICAL_CREDIT_NOTE_AMOUNT_PRESENT",
                      source["source_review_flags"])
        self.assertFalse(source["credit_note_eligible"])

    def test_verified_lookup_failure_is_not_treated_as_absence(self):
        def broken(_):
            raise RuntimeError("mock auth unavailable")
        with self.assertRaisesRegex(HistoricalInvoiceEvidenceUnavailable,
                                    "HISTORICAL_REPORT_SOURCE_UNAVAILABLE"):
            lookup_historical_evidence(["MXP98007"],verified_lookup=broken)

    def test_data_source_cannot_be_substituted_without_attestation(self):
        item = report(["MXP98008"])
        item["source_kind"] = "USER_UPLOADED_SPREADSHEET"
        with self.assertRaisesRegex(HistoricalInvoiceEvidenceUnavailable,
                                    "HISTORICAL_LOOKUP_CONTRACT_INVALID"):
            project_historical_evidence(["MXP98008"],item)

    def test_silent_financial_rounding_not_authorized(self):
        item = report(["MXP98009"],overrides={13:"1000.004"})
        source = project_historical_evidence(["MXP98009"],item)["records"][0]
        self.assertIn("SOURCE_FINANCIAL_VALUE_REQUIRES_REVIEW",
                      source["source_review_flags"])
        self.assertIsNone(source["taxable_source"])


if __name__ == "__main__":
    unittest.main()
