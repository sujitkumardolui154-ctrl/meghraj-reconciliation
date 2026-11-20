"""D-031 fully fabricated isolated receipt, replay and separation-of-duties QA."""
from concurrent.futures import ThreadPoolExecutor
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "staging/aws_login_v150"))
import d030_future_payment_provenance as sidecar_contract
from d031_synthetic_receipt_register import (
    MockPrincipal, MockServerPolicy, SyntheticOnlyReceiptRegister,
    SyntheticRegistryBlocked, UPLOADER, REVIEWER,
)

UP = MockPrincipal("SYNTH-USER-ALICE", UPLOADER)
REVIEW = MockPrincipal("SYNTH-USER-BOB", REVIEWER)


def policy():
    return MockServerPolicy(
        activation_date="2026-12-01",
        submission_date="2026-12-03",
        uploader_uid=UP.uid,
        reviewer_uid=REVIEW.uid,
    )


def fixture(*, reference="SYNTH-UTR-0001", bank_date="2026-12-02",
            desc="SYNTH-POSTAGE AUG-26", credit="125.00"):
    row = {"Description":desc, "SOL ID":"001505", "Credit Amount":credit}
    meta = {
        "source_kind":"SYNTHETIC",
        "excel_row":2,
        "bank_date":bank_date,
        "bank_reference":reference,
        "source_credit_column":"PAYMNENT!I",
        "source_credit_I":credit,
        "evidence_row_sha256":sidecar_contract.evidence_row_sha256(row),
    }
    return [row], [meta]


class D031SyntheticReceiptRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = SyntheticOnlyReceiptRegister(server_policy=policy())
        self.addCleanup(self.registry.close)

    def stage(self, rows=None, metadata=None, principal=UP):
        if rows is None:
            rows, metadata = fixture()
        return self.registry.stage_mock_evidence(
            rows, metadata, principal=principal)

    def test_stage_and_review_are_only_fake_and_never_financial(self):
        rows, sidecar = fixture()
        immutable_rows = copy.deepcopy(rows)
        immutable_meta = copy.deepcopy(sidecar)
        response = self.stage(rows, sidecar)
        self.assertEqual(response["status"], "SYNTHETIC_PENDING_REVIEW")
        self.assertTrue(response["mock_receipt_created"])
        self.assertTrue(response["mock_reference_registered"])
        self.assertFalse(response["persistent_receipt_written"])
        self.assertFalse(response["actual_user_authenticated"])
        self.assertFalse(response["real_bank_authority_verified"])
        self.assertFalse(response["financial_writes"])
        self.assertFalse(response["live_financial_unlock_allowed"])
        self.assertFalse(response["historical_financial_records_accessed"])
        self.assertTrue(response["receipt_id"].startswith("SYNTH-RCPT-"))
        self.assertEqual(rows, immutable_rows)
        self.assertEqual(sidecar, immutable_meta)
        reviewed = self.registry.review_mock_receipt(
            response["receipt_id"], principal=REVIEW)
        self.assertEqual(reviewed["status"], "SYNTHETIC_REVIEWED_NO_ALLOCATION")
        self.assertTrue(reviewed["mock_review_completed"])
        self.assertFalse(reviewed["financial_reconciliation_executed"])
        self.assertFalse(reviewed["financial_writes"])
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_reference_hashes"], 1)

    def test_identical_batch_is_idempotent_without_a_second_write(self):
        first = self.stage()
        second = self.stage()
        self.assertEqual(first["receipt_id"], second["receipt_id"])
        self.assertTrue(second["idempotent_replay"])
        self.assertFalse(second["mock_receipt_created"])
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"], 1)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_reference_hashes"], 1)

    def test_same_fake_utr_different_batch_is_held(self):
        self.stage()
        other, side = fixture(desc="SYNTH-SECOND SOURCE",credit="77.00")
        bad = self.stage(other, side)
        self.assertEqual(bad["status"], "HELD_NO_MOCK_RECEIPT")
        self.assertIn("MOCK_UTR_ALREADY_REGISTERED",
                      str(bad["holds"]))
        self.assertFalse(bad["mock_receipt_created"])
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"], 1)

    def test_old_bank_date_rejected_before_in_memory_receipt(self):
        rows, side = fixture(bank_date="2026-11-30")
        res = self.stage(rows, side)
        self.assertIn("PRE_ACTIVATION_BANK_DATE_FORBIDDEN", str(res["holds"]))
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"],0)

    def test_bad_synthetic_utr_is_denied(self):
        r, m = fixture()
        m[0]["bank_reference"] = "REAL-UTR-001"
        result = self.stage(r,m)
        self.assertIn("BANK_REFERENCE_INVALID", str(result["holds"]))
        self.assertFalse(result["financial_writes"])

    def test_upload_actor_and_role_are_mock_scoped(self):
        for actor in (
            MockPrincipal("SYNTH-USER-MALLORY", UPLOADER),
            MockPrincipal(UP.uid, REVIEWER),
            MockPrincipal(REVIEW.uid, REVIEWER),
            {"uid":UP.uid,"role":UPLOADER},
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(SyntheticRegistryBlocked):
                    self.stage(principal=actor)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"],0)

    def test_review_requires_distinct_mock_review_role_and_actor(self):
        rid = self.stage()["receipt_id"]
        for actor in (
            UP,
            MockPrincipal(UP.uid, REVIEWER),
            MockPrincipal("SYNTH-USER-MALLORY", REVIEWER),
            MockPrincipal(REVIEW.uid, UPLOADER),
        ):
            with self.subTest(actor=actor):
                with self.assertRaises(SyntheticRegistryBlocked):
                    self.registry.review_mock_receipt(rid,principal=actor)
        result=self.registry.review_mock_receipt(rid,principal=REVIEW)
        self.assertTrue(result["mock_review_completed"])

    def test_review_cannot_be_repeated_or_applied_to_unknown_receipt(self):
        rid=self.stage()["receipt_id"]
        self.registry.review_mock_receipt(rid,principal=REVIEW)
        with self.assertRaisesRegex(SyntheticRegistryBlocked,"MOCK_REVIEW_STATE_INVALID"):
            self.registry.review_mock_receipt(rid,principal=REVIEW)
        with self.assertRaisesRegex(SyntheticRegistryBlocked,"MOCK_RECEIPT_NOT_FOUND"):
            self.registry.review_mock_receipt("SYNTH-RCPT-"+"A"*24,principal=REVIEW)
        with self.assertRaisesRegex(SyntheticRegistryBlocked,"MOCK_RECEIPT_ID_INVALID"):
            self.registry.review_mock_receipt("live-bank-receipt",principal=REVIEW)

    def test_mock_policy_fail_closed_on_real_or_same_uid(self):
        for bad_policy in (
            MockServerPolicy("2026-12-01","2026-12-03",UP.uid,UP.uid),
            MockServerPolicy("2026-12-01","2026-12-03","actual-user",REVIEW.uid),
            MockServerPolicy("2026-12-01","2026-12-03",UP.uid,REVIEW.uid,False),
            MockServerPolicy("2026-12-10","2026-12-03",UP.uid,REVIEW.uid),
            dict(activation_date="2026-12-01"),
        ):
            with self.subTest(policy=bad_policy):
                with self.assertRaises((SyntheticRegistryBlocked,sidecar_contract.FutureEvidenceBlocked)):
                    SyntheticOnlyReceiptRegister(server_policy=bad_policy)

    def test_no_client_supplied_cutoff_override_argument(self):
        rows, sidecar = fixture(bank_date="2026-11-30")
        with self.assertRaises(TypeError):
            self.registry.stage_mock_evidence(
                rows,sidecar,principal=UP,activation_date="2026-11-01")
        self.assertEqual(self.stage(rows,sidecar)["status"],
                         "HELD_NO_MOCK_RECEIPT")

    def test_attempted_production_flag_in_sidecar_is_held(self):
        rows, sidecar=fixture()
        sidecar[0]["production_unlock_allowed"]=True
        result=self.stage(rows,sidecar)
        self.assertIn("PROVENANCE_SCHEMA_MISMATCH",str(result["holds"]))
        self.assertFalse(result["financial_writes"])

    def test_batch_two_rows_atomic_when_one_claim_is_bad(self):
        first, a=fixture()
        second,b=fixture(desc="SYNTH-SECOND SOURCE",credit="50.00",
                         reference="SYNTH-UTR-0002")
        b[0]["excel_row"]=3
        b[0]["source_credit_I"]="51.00"
        result=self.stage(first+second,a+b)
        self.assertEqual(result["status"],"HELD_NO_MOCK_RECEIPT")
        self.assertIn("ORIGINAL_CREDIT_I_MISMATCH",str(result["holds"]))
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"],0)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_reference_hashes"],0)

    def test_concurrent_fake_duplicate_submissions_only_one_receipt(self):
        rows,sidecar=fixture()
        with ThreadPoolExecutor(max_workers=3) as pool:
            outputs=list(pool.map(lambda _: self.stage(rows,sidecar),range(3)))
        self.assertEqual(sum(r["mock_receipt_created"] for r in outputs),1)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_receipts"],1)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_reference_hashes"],1)

    def test_concurrent_conflicting_utr_never_creates_two_receipts(self):
        r1,m1=fixture()
        r2,m2=fixture(desc="SYNTH-SECOND SOURCE", credit="15.00")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(self.stage,r1,m1)
            b=pool.submit(self.stage,r2,m2)
            responses=[a.result(),b.result()]
        self.assertEqual(sum(x["mock_receipt_created"] for x in responses),1)
        self.assertEqual(self.registry.mock_counts(principal=REVIEW)["mock_reference_hashes"],1)

    def test_mock_count_access_requires_reviewer(self):
        with self.assertRaises(SyntheticRegistryBlocked):
            self.registry.mock_counts(principal=UP)
        counts=self.registry.mock_counts(principal=REVIEW)
        self.assertFalse(counts["production_unlock_allowed"])
        self.assertFalse(counts["persistent_receipts"])
        self.assertFalse(counts["financial_writes"])

    def test_existing_three_column_html_and_finance_lock_remain_unchanged(self):
        html=(ROOT / "dashboard_source/index.html").read_text()
        self.assertIn('id="dil-payment-upload-form"',html)
        self.assertIn('id="dil-payment-reconcile" disabled',html)
        self.assertIn("Description | SOL ID | Credit Amount",html)
        self.assertNotIn("d031_synthetic_receipt_register",html)
        app=(ROOT / "staging/aws_login_v150/app.py").read_text()
        self.assertNotIn("d031_synthetic_receipt_register",app)
        self.assertIn("def disabled_financial_api(",app)


if __name__=="__main__":
    unittest.main()
