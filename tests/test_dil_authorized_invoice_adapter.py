"""Synthetic tests for explicit DIL per-record authorization. No financial data."""
import unittest
from functools import partial
from dashboard_source.dil_invoice_intelligence_pipeline import (
    DraftAnswer, IntelligenceUnavailable, VerifiedCaller,
    execute_invoice_question,
)
from dashboard_source.dil_authorized_invoice_adapter import (
    CandidateRow, TrustedScope, authorized_invoice_reader,
)


class AuthorizedReadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.caller = VerifiedCaller("tester-a", frozenset({"sbi_invoice_reader"}))
        self.scope = TrustedScope("tester-a", "sbi-approved-group", True)
        self.row = CandidateRow(
            "invoice", "MXP-TEST-001", "sha256:abc", "2026-11-04T00:00:00Z",
            "Synthetic invoice reviewed amount 100", "sbi-approved-group"
        )
        self.read_count = 0
        self.policy_count = 0
        self.compose_count = 0

    def fetch(self, question, limit):
        self.read_count += 1
        self.assertEqual(limit, 25)
        return (self.row,)

    def policy(self, scope, row):
        self.policy_count += 1
        return scope.verified and row.scope == scope.scope

    def reader(self, caller=None, scope=None, fetch=None, policy=None):
        return partial(
            authorized_invoice_reader,
            verified_scope=scope or self.scope,
            read_candidates=fetch or self.fetch,
            can_read=policy or self.policy,
        )

    def compose(self, query, history, evidence):
        self.compose_count += 1
        return DraftAnswer("Synthetic invoice evidence is available.",
                           ("invoice:MXP-TEST-001",))

    def test_end_to_end_synthetic_evidence_before_answer(self):
        result = execute_invoice_question(
            self.caller, "Compare invoice changes for all available periods", (),
            self.reader(), self.compose
        )
        self.assertEqual(result.citations[0].record_id, "MXP-TEST-001")
        self.assertEqual((self.read_count, self.policy_count, self.compose_count),
                         (1, 1, 1))

    def test_denied_scope_never_reads_or_composes(self):
        bad = TrustedScope("another-user", "sbi-approved-group", True)
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(self.caller, "Any invoice?", (),
                                     self.reader(scope=bad), self.compose)
        self.assertEqual((self.read_count, self.policy_count, self.compose_count),
                         (0, 0, 0))

    def test_missing_scope_validation_denied(self):
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(scope=TrustedScope("tester-a", "sbi-approved-group", False)),
                self.compose,
            )
        self.assertEqual(self.read_count, 0)

    def test_negative_per_record_policy_denied_before_composition(self):
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(policy=lambda *_: False), self.compose
            )
        self.assertEqual(self.compose_count, 0)

    def test_truthy_nonboolean_policy_decision_is_denied(self):
        # A misconfigured policy returning a string or integer must not grant access.
        for decision in ("allow", 1, {"allowed": True}):
            with self.subTest(decision=decision), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(policy=lambda *_: decision), self.compose
                )
        self.assertEqual(self.compose_count, 0)

    def test_cross_scope_is_never_partially_answered(self):
        different = CandidateRow(
            "invoice", "MXP-TEST-002", "sha256:def", "2026-11-04T00:00:00Z",
            "Different branch", "unauthorized-scope"
        )
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(fetch=lambda *_: (self.row, different)), self.compose
            )
        self.assertEqual(self.compose_count, 0)

    def test_duplicate_record_is_denied_before_answer(self):
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(fetch=lambda *_: (self.row, self.row)), self.compose
            )
        self.assertEqual(self.compose_count, 0)

    def test_overlimit_batch_rejected_without_composition(self):
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(fetch=lambda *_: tuple(self.row for _ in range(26))),
                self.compose
            )
        self.assertEqual(self.compose_count, 0)

    def test_no_live_data_or_financial_write(self):
        self.assertEqual(self.row.excerpt, "Synthetic invoice reviewed amount 100")


if __name__ == "__main__":
    unittest.main()
