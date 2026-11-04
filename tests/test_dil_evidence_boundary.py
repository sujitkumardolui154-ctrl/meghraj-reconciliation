"""Synthetic F02 evidence boundary regression; no external I/O or writes."""
import unittest
from dataclasses import replace
from dashboard_source.dil_evidence_boundary import (
    Evidence, EvidenceDenied, Principal, authorize_evidence, MAX_EVIDENCE
)


class EvidenceBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.user = Principal("user-a", "tenant-a", frozenset({"invoice_reader"}))
        self.row = Evidence("invoice", "INV-001", "tenant-a", "user-a",
                            "invoice_reader", "sha256:abc", "2026-11-04T00:00:00Z",
                            {"invoice_no": "INV-001"})

    def test_authorized_synthetic_row_is_not_modified(self):
        before = dict(self.row.fields)
        self.assertEqual(authorize_evidence(self.user, [self.row]), (self.row,))
        self.assertEqual(self.row.fields, before)

    def test_revoked_or_missing_identity_denied(self):
        for principal in (replace(self.user, revoked=True), None,
                          replace(self.user, roles=frozenset())):
            with self.subTest(principal=principal), self.assertRaises(EvidenceDenied):
                authorize_evidence(principal, [self.row])

    def test_cross_user_cross_tenant_and_role_denied(self):
        for row in (replace(self.row, owner_uid="user-b"),
                    replace(self.row, tenant="tenant-b"),
                    replace(self.row, required_role="finance_admin")):
            with self.subTest(row=row), self.assertRaises(EvidenceDenied):
                authorize_evidence(self.user, [row])

    def test_unknown_source_missing_provenance_duplicate_and_limit_denied(self):
        for rows in ([replace(self.row, source="raw_firestore")],
                     [replace(self.row, version="")],
                     [self.row, self.row],
                     [replace(self.row, record_id=str(i)) for i in range(MAX_EVIDENCE + 1)]):
            with self.subTest(count=len(rows)), self.assertRaises(EvidenceDenied):
                authorize_evidence(self.user, rows)

    def test_atomic_failure_does_not_return_partial_authorized_data(self):
        with self.assertRaises(EvidenceDenied):
            authorize_evidence(self.user, [self.row, replace(self.row, owner_uid="other", record_id="2")])


if __name__ == "__main__":
    unittest.main()
