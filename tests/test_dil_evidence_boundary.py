"""Synthetic F02 evidence-boundary regression. No external connections."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend_source"))
from dil_evidence_boundary import AccessDenied, Evidence, Principal, cite, decimal_total, retrieve


class EvidenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.user = Principal("user1", "tenant1", frozenset({"analyst"}), True)
        self.record = Evidence("invoice", "row:17", "tenant1", frozenset({"analyst"}), "sha:abc", {"amount": "10.00"})

    def fetch(self, tenant, query, limit):
        self.assertEqual(tenant, "tenant1")
        return [self.record]

    def test_authorized_with_provenance(self):
        result = retrieve(self.user, "show invoice", "invoice", self.fetch)
        self.assertEqual(cite(result[0]), "invoice:row:17@sha:abc")

    def test_inactive_denied(self):
        with self.assertRaises(AccessDenied):
            retrieve(Principal("u", "tenant1", frozenset({"analyst"}), False), "show", "invoice", self.fetch)

    def test_wrong_tenant_denied(self):
        self.record = Evidence("invoice", "17", "other", frozenset({"analyst"}), "v1", {})
        with self.assertRaises(AccessDenied):
            retrieve(self.user, "show", "invoice", self.fetch)

    def test_wrong_role_denied(self):
        self.record = Evidence("invoice", "17", "tenant1", frozenset({"admin"}), "v1", {})
        with self.assertRaises(AccessDenied):
            retrieve(self.user, "show", "invoice", self.fetch)

    def test_source_substitution_denied(self):
        self.record = Evidence("payment", "17", "tenant1", frozenset({"analyst"}), "v1", {})
        with self.assertRaises(AccessDenied):
            retrieve(self.user, "show", "invoice", self.fetch)

    def test_missing_version_denied(self):
        self.record = Evidence("invoice", "17", "tenant1", frozenset({"analyst"}), "", {})
        with self.assertRaises(AccessDenied):
            retrieve(self.user, "show", "invoice", self.fetch)

    def test_overfetch_denied(self):
        with self.assertRaises(AccessDenied):
            retrieve(self.user, "show", "invoice", lambda t, q, n: [self.record] * (n + 1))

    def test_invalid_source_denied(self):
        with self.assertRaises(ValueError):
            retrieve(self.user, "show", "admin", self.fetch)

    def test_query_limit_denied(self):
        with self.assertRaises(ValueError):
            retrieve(self.user, "x" * 2001, "invoice", self.fetch)

    def test_decimal_exact(self):
        self.assertEqual(decimal_total(["0.10", "0.20"]), decimal_total(["0.30"]))

    def test_nan_denied(self):
        with self.assertRaises(ValueError):
            decimal_total(["NaN"])

    def test_no_mutation(self):
        before = dict(self.record.fields)
        retrieve(self.user, "show", "invoice", self.fetch)
        self.assertEqual(before, self.record.fields)


if __name__ == "__main__":
    unittest.main()
