"""Offline F04 security and exact-arithmetic regression; no external services."""
import unittest
from backend_source.dil_evidence_boundary import EvidenceDenied, select_evidence, exact_money_sum

P = {"uid": "u1", "tenant": "t1", "authenticated": True,
     "revoked": False, "roles": ["sbi_invoice_reader"]}
R = {"authorized_uid": "u1", "tenant": "t1", "source_version": "v1",
     "source": "invoice", "row_id": "35:9", "reference": "MXP1",
     "source_timestamp": "2026-11-01T00:00:00Z", "summary": "synthetic"}

class EvidenceBoundaryTests(unittest.TestCase):
    def select(self, principal=None, records=None):
        return select_evidence(principal=P if principal is None else principal,
                               records=[R] if records is None else records,
                               tenant="t1", source_version="v1")

    def test_authorized_citation(self):
        self.assertEqual(self.select()[0]["citation"], "invoice:35:9@v1")

    def test_unauthenticated(self):
        with self.assertRaises(EvidenceDenied):
            self.select({**P, "authenticated": False})

    def test_revoked(self):
        with self.assertRaises(EvidenceDenied):
            self.select({**P, "revoked": True})

    def test_missing_revocation_proof(self):
        with self.assertRaises(EvidenceDenied):
            self.select({k:v for k,v in P.items() if k != "revoked"})

    def test_missing_role(self):
        with self.assertRaises(EvidenceDenied):
            self.select({**P, "roles": []})

    def test_cross_tenant(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[{**R, "tenant": "other"}])

    def test_cross_user(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[{**R, "authorized_uid": "u2"}])

    def test_stale_version(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[{**R, "source_version": "v0"}])

    def test_unknown_source(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[{**R, "source": "secrets"}])

    def test_duplicate_row(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[R, R])

    def test_bounded_page(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[R] * 51)

    def test_bounded_summary(self):
        with self.assertRaises(EvidenceDenied):
            self.select(records=[{**R, "summary": "x"*2001}])

    def test_decimal_sum(self):
        self.assertEqual(exact_money_sum(["0.10", "0.20"]), "0.30")

    def test_reject_float(self):
        with self.assertRaises(EvidenceDenied):
            exact_money_sum([0.1])

    def test_reject_nan(self):
        with self.assertRaises(EvidenceDenied):
            exact_money_sum(["NaN"])

    def test_reject_subpaisa(self):
        with self.assertRaises(EvidenceDenied):
            exact_money_sum(["0.001"])

if __name__ == "__main__":
    unittest.main()
