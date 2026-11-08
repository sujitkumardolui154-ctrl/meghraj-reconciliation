import unittest
from decimal import Decimal
from backend_source.dil_evidence_envelope import EvidenceRejected, exact_money, validate_answer

ROW = {"source":"invoice","ref":"row:synthetic:7","version":"sha256:synthetic","observed_at":"2026-11-09T00:00:00Z"}
def envelope(**changes):
    result={"answer":"Synthetic invoice exists","status":"GROUNDED","evidence":[dict(ROW)]}
    result.update(changes)
    return result

class EvidenceEnvelopeTests(unittest.TestCase):
    def test_authorized_grounded(self):
        self.assertEqual(validate_answer(envelope(), authorized_refs=frozenset({ROW["ref"]}))["evidence"], [ROW])
    def test_unauthorized_ref_denied(self):
        with self.assertRaisesRegex(EvidenceRejected, "UNAUTHORIZED"):
            validate_answer(envelope(), authorized_refs=frozenset())
    def test_empty_grounded_denied(self):
        with self.assertRaisesRegex(EvidenceRejected, "MISSING_EVIDENCE"):
            validate_answer(envelope(evidence=[]), authorized_refs=frozenset())
    def test_missing_version_denied(self):
        with self.assertRaisesRegex(EvidenceRejected, "UNVERSIONED"):
            validate_answer(envelope(evidence=[dict(ROW, version="")]), authorized_refs=frozenset({ROW["ref"]}))
    def test_unknown_source_denied(self):
        with self.assertRaises(EvidenceRejected):
            validate_answer(envelope(evidence=[dict(ROW, source="admin")]), authorized_refs=frozenset({ROW["ref"]}))
    def test_duplicate_denied(self):
        with self.assertRaises(EvidenceRejected):
            validate_answer(envelope(evidence=[ROW,ROW]), authorized_refs=frozenset({ROW["ref"]}))
    def test_unexpected_field_denied(self):
        with self.assertRaises(EvidenceRejected):
            validate_answer(envelope(secret="token"), authorized_refs=frozenset({ROW["ref"]}))
    def test_bounded_answer(self):
        with self.assertRaises(EvidenceRejected):
            validate_answer(envelope(answer="x"*4001), authorized_refs=frozenset({ROW["ref"]}))
    def test_no_evidence_unknown_allowed(self):
        result=validate_answer(envelope(answer="No verified evidence",status="INSUFFICIENT_EVIDENCE",evidence=[]), authorized_refs=frozenset())
        self.assertEqual(result["evidence"],[])
    def test_money_exact(self):
        self.assertEqual(exact_money("0.10")+exact_money("0.20"), Decimal("0.30"))
    def test_money_float_denied(self):
        with self.assertRaises(EvidenceRejected): exact_money(0.1)
    def test_money_nan_denied(self):
        with self.assertRaises(EvidenceRejected): exact_money("NaN")
    def test_money_precision_denied(self):
        with self.assertRaises(EvidenceRejected): exact_money("1.001")

if __name__=="__main__":
    unittest.main()
