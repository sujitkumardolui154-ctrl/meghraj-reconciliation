"""Synthetic no-network F43 boundary regressions."""
import unittest
from backend_source.dil_evidence_boundary import (
    Evidence, EvidenceDenied, VerifiedScope, authorized_evidence, evidence_answer, money
)

HASH = "a" * 64
SCOPE = VerifiedScope("user-1", "tenant-1", frozenset({"001"}), True)


def row(sol="001", digest=HASH):
    return Evidence("synthetic-master", digest, 3, "MXP123", sol, {"taxable": "100.00"})


class BoundaryTests(unittest.TestCase):
    def test_authorized_row_citation(self):
        found = authorized_evidence("Show invoice", SCOPE, lambda q, n: [row()])
        self.assertEqual(found[0].citation, f"synthetic-master@{HASH}:row-3")

    def test_no_evidence_is_not_verified(self):
        self.assertEqual(evidence_answer([])["status"], "NOT_VERIFIABLE")

    def test_no_session(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", VerifiedScope("u", "t", frozenset({"001"}), False), lambda q, n: [row()])

    def test_revoked_session(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", VerifiedScope("u", "t", frozenset({"001"}), True, True), lambda q, n: [row()])

    def test_empty_scope(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", VerifiedScope("u", "t", frozenset(), True), lambda q, n: [row()])

    def test_cross_sol_fails_entire_batch(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", SCOPE, lambda q, n: [row(), row("002")])

    def test_bad_provenance(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", SCOPE, lambda q, n: [row(digest="not-a-hash")])

    def test_unbounded_source(self):
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", SCOPE, lambda q, n: [row()] * 51)

    def test_query_limit(self):
        with self.assertRaises(ValueError):
            authorized_evidence("x" * 2001, SCOPE, lambda q, n: [])

    def test_row_limit(self):
        with self.assertRaises(ValueError):
            authorized_evidence("invoice", SCOPE, lambda q, n: [], limit=1000)

    def test_money_strict(self):
        self.assertEqual(money("100.01"), money("100") + money("0.01"))
        for value in ("NaN", "Infinity", "garbage"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                money(value)

    def test_no_fetch_on_invalid_auth(self):
        calls = []
        with self.assertRaises(EvidenceDenied):
            authorized_evidence("invoice", VerifiedScope("", "", frozenset(), False), lambda q, n: calls.append(1))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
