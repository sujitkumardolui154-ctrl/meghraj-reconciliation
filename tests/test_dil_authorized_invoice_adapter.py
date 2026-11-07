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

    def fetch(self, verified_scope, question, limit):
        self.assertIs(verified_scope, self.scope)
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

    def test_repository_receives_explicit_verified_scope_before_read(self):
        captured = []
        def scoped_fetch(scope, question, limit):
            captured.append((scope, question, limit))
            return (self.row,)
        execute_invoice_question(
            self.caller, "Find invoice evidence", (),
            self.reader(fetch=scoped_fetch), self.compose,
        )
        self.assertEqual(captured, [(self.scope, "Find invoice evidence", 25)])

    def test_repository_rejects_unscoped_callback_fail_closed(self):
        # A legacy two-argument repository cannot silently ignore scope.
        def legacy_reader(question, limit):
            return (self.row,)
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(fetch=legacy_reader), self.compose,
            )
        self.assertEqual(self.compose_count, 0)

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

    def test_truthy_nonboolean_scope_verification_is_denied_before_read(self):
        # A string, number or object must never stand in for verified auth.
        for value in ("verified", 1, {"verified": True}):
            with self.subTest(value=value), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(scope=TrustedScope("tester-a", "sbi-approved-group", value)),
                    self.compose,
                )
        self.assertEqual((self.read_count, self.policy_count, self.compose_count),
                         (0, 0, 0))

    def test_invalid_scope_types_denied_before_read(self):
        for scope_value in (1, {"branch": "x"}, ["branch"], "   "):
            with self.subTest(scope=scope_value), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(scope=TrustedScope("tester-a", scope_value, True)),
                    self.compose,
                )
        self.assertEqual((self.read_count, self.policy_count, self.compose_count),
                         (0, 0, 0))

    def test_invalid_candidate_scope_denied_before_composition(self):
        for scope_value in (1, {"branch": "x"}, "   "):
            bad = CandidateRow(
                "invoice", "MXP-TEST-001", "sha256:abc",
                "2026-11-04T00:00:00Z", "Synthetic invoice", scope_value
            )
            with self.subTest(scope=scope_value), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(fetch=lambda *_: (bad,)), self.compose,
                )
        self.assertEqual(self.compose_count, 0)

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

    def test_malformed_unhashable_evidence_kind_fails_closed(self):
        # Repository bugs must never escape as raw TypeError or reach composer.
        for kind in (["invoice"], {"kind": "invoice"}):
            bad = CandidateRow(
                kind, "MXP-TEST-001", "sha256:abc",
                "2026-11-04T00:00:00Z", "Synthetic invoice",
                "sbi-approved-group",
            )
            with self.subTest(kind=kind), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(fetch=lambda *_: (bad,)), self.compose,
                )
        self.assertEqual(self.policy_count, 0)
        self.assertEqual(self.compose_count, 0)

    def test_missing_provenance_denied_before_policy_callback(self):
        for field in ("record_id", "version", "observed_at", "excerpt"):
            values = dict(kind="invoice", record_id="MXP-TEST-001",
                          version="sha256:abc", observed_at="2026-11-04T00:00:00Z",
                          excerpt="Synthetic evidence", scope="sbi-approved-group")
            values[field] = "   "
            malformed = CandidateRow(**values)
            with self.subTest(field=field), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    self.caller, "Invoice?", (),
                    self.reader(fetch=lambda *_: (malformed,)), self.compose,
                )
        self.assertEqual(self.policy_count, 0)
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

    def test_repository_exception_fails_closed_before_policy_or_composition(self):
        def broken_reader(*_):
            raise RuntimeError("synthetic repository internal detail")
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(fetch=broken_reader), self.compose
            )
        self.assertEqual((self.policy_count, self.compose_count), (0, 0))

    def test_policy_exception_fails_closed_before_composition(self):
        def broken_policy(*_):
            raise RuntimeError("synthetic authorization internal detail")
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                self.caller, "Invoice?", (),
                self.reader(policy=broken_policy), self.compose
            )
        self.assertEqual(self.compose_count, 0)

    def test_malformed_identity_and_permissions_denied_before_repository_read(self):
        # String permissions can satisfy Python substring membership but are not
        # verified permission sets. Blank identities cannot establish ownership.
        bad_callers = (
            VerifiedCaller("tester-a", "sbi_invoice_reader"),
            VerifiedCaller("tester-a", ["sbi_invoice_reader"]),
            VerifiedCaller("   ", frozenset({"sbi_invoice_reader"})),
        )
        for caller in bad_callers:
            with self.subTest(caller=caller), self.assertRaises(IntelligenceUnavailable):
                execute_invoice_question(
                    caller, "Invoice?", (), self.reader(), self.compose
                )
        bad_scope = TrustedScope("   ", "sbi-approved-group", True)
        with self.assertRaises(IntelligenceUnavailable):
            execute_invoice_question(
                VerifiedCaller("   ", frozenset({"sbi_invoice_reader"})),
                "Invoice?", (), self.reader(scope=bad_scope), self.compose
            )
        self.assertEqual((self.read_count, self.policy_count, self.compose_count), (0, 0, 0))

    def test_falsey_nonboolean_revocation_denied_at_adapter_boundary(self):
        # Adapter may be invoked independently of the orchestration pipeline.
        # Falsey claims are not equivalent to an explicitly verified False.
        for claim in (0, None, "", [], {}):
            caller = VerifiedCaller(
                "tester-a", frozenset({"sbi_invoice_reader"}), claim
            )
            with self.subTest(claim=claim), self.assertRaises(IntelligenceUnavailable):
                authorized_invoice_reader(
                    caller, "Invoice?", (), 25,
                    verified_scope=self.scope,
                    read_candidates=self.fetch,
                    can_read=self.policy,
                )
        self.assertEqual((self.read_count, self.policy_count), (0, 0))

    def test_no_live_data_or_financial_write(self):
        self.assertEqual(self.row.excerpt, "Synthetic invoice reviewed amount 100")


if __name__ == "__main__":
    unittest.main()
