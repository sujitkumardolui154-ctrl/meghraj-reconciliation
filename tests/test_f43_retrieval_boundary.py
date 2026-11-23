"""F43 synthetic retrieval boundary: deny first, no financial writes."""
import unittest
from dashboard_source.dil_readonly_orchestrator import Principal, RetrievalDenied, retrieve


class FakeAdapter:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def search_readonly(self, *, query, uid, role, limit):
        self.calls.append((query, uid, role, limit))
        return self.rows


def row(**changes):
    data = dict(source_id="invoice:synthetic-1", source_version="snapshot-v1",
                authorized_uid="alice", allowed_roles=["invoice_viewer"],
                authorized=True, snippet="Synthetic invoice, status pending", amount="100.25")
    data.update(changes)
    return data


class RetrievalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("alice", "invoice_viewer", True)
        self.adapter = FakeAdapter([row()])

    def test_authorized_evidence_has_exact_citation(self):
        out = retrieve("Show my invoice", principal=self.principal, adapter=self.adapter)
        self.assertEqual(out["status"], "EVIDENCE_ONLY")
        self.assertEqual(out["evidence"][0]["source_id"], "invoice:synthetic-1")
        self.assertEqual(out["evidence"][0]["amount"], "100.25")
        self.assertEqual(self.adapter.calls[0][3], 20)

    def test_arbitrary_natural_language_and_context(self):
        out = retrieve("Compare this with last quarter, why?", principal=self.principal,
                       adapter=self.adapter, context=["Which SOL?", "Compare them"])
        self.assertEqual(out["status"], "EVIDENCE_ONLY")

    def test_revoked_denied_before_adapter(self):
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=Principal("alice", "invoice_viewer", True, True), adapter=self.adapter)
        self.assertEqual(self.adapter.calls, [])

    def test_unverified_denied_before_adapter(self):
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=Principal("alice", "invoice_viewer", False), adapter=self.adapter)
        self.assertEqual(self.adapter.calls, [])

    def test_cross_user_denied(self):
        self.adapter.rows = [row(authorized_uid="bob")]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_role_denied(self):
        self.adapter.rows = [row(allowed_roles=["admin"])]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_unverified_record_denied(self):
        self.adapter.rows = [row(authorized=False)]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_duplicate_sources_denied(self):
        self.adapter.rows = [row(), row()]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_bad_amount_denied(self):
        self.adapter.rows = [row(amount="1e999")]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_bounded_result_set(self):
        self.adapter.rows = [row(source_id="invoice:synthetic-"+str(i)) for i in range(21)]
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=self.adapter)

    def test_no_evidence_is_not_verifiable(self):
        self.adapter.rows = []
        out = retrieve("x", principal=self.principal, adapter=self.adapter)
        self.assertEqual(out["status"], "NOT_VERIFIABLE")

    def test_missing_adapter_denied(self):
        with self.assertRaises(RetrievalDenied):
            retrieve("x", principal=self.principal, adapter=object())

    def test_no_mutation_interface(self):
        self.assertFalse(hasattr(self.adapter, "write"))
        self.assertFalse(hasattr(self.adapter, "update"))
        retrieve("x", principal=self.principal, adapter=self.adapter)
        self.assertEqual(len(self.adapter.calls), 1)


if __name__ == "__main__":
    unittest.main()
