"""New Stage 3 synthetic-only review/ledger integration regression.

No real UTR, invoice, payment, bank statement, finance DB or disk ledger.
"""
import copy
import threading
import unittest

from d030_future_payment_provenance import evidence_row_sha256
from d031_synthetic_receipt_register import (
    MockPrincipal, MockServerPolicy, REVIEWER, UPLOADER,
)
from stage3_mock_bridge import Stage3MockBridge, Stage3MockBlocked


def fake_invoice(ident="SYNTH-INV-A", gross="118.00", tds=1):
    return dict(source_kind="SYNTHETIC", invoice_no=ident, sol_id="1505",
                client_name="SYNTH BRANCH", sbisa=False,
                invoice_date="2026-11-21", service_months=["2026-11"],
                taxable="100.00", cgst="9.00", sgst="9.00", gross=gross,
                approved_tds_rate=tds, original_paid_marker=None,
                source_verified=True, master_verified=True,
                protected_prior=False, credit_note=False)


def fake_row(ident="A", credit="117.00"):
    return {"Description": f"SYNTH-{ident} POSTAGE NOVEMBER 2026",
            "SOL ID": "1505", "Credit Amount": credit}


def mock_pair(ident="A", credit="117.00"):
    source = fake_row(ident, credit)
    utr = "SYNTH-UTR-" + ident
    meta = {"source_kind":"SYNTHETIC", "excel_row":2,
            "bank_date":"2026-11-23", "bank_reference":utr,
            "source_credit_column":"PAYMNENT!I", "source_credit_I":credit,
            "evidence_row_sha256": evidence_row_sha256(source)}
    ctx = {"source_kind":"SYNTHETIC", "bank_reference":utr,
           "client_name":"SYNTH BRANCH", "invoice_refs":["SYNTH-INV-A"],
           "sbisa":False, "source_verified":True,
           "bank_reference_verified":True}
    return source, meta, ctx


class Stage3IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = MockServerPolicy(activation_date="2026-11-21",
                                       submission_date="2026-11-24",
                                       uploader_uid="SYNTH-USER-UPLOADER",
                                       reviewer_uid="SYNTH-USER-REVIEWER")
        self.uploader = MockPrincipal(uid="SYNTH-USER-UPLOADER",role=UPLOADER)
        self.reviewer = MockPrincipal(uid="SYNTH-USER-REVIEWER",role=REVIEWER)
        self.work = Stage3MockBridge(server_policy=self.policy)

    def tearDown(self):
        self.work.close()

    def create(self, ident="A", credit="117.00"):
        row, sidecar, ctx=mock_pair(ident,credit)
        rec=self.work.stage([row],[sidecar],principal=self.uploader)
        self.assertTrue(rec["mock_receipt_created"])
        return rec["receipt_id"],row,sidecar,ctx

    def review(self, receipt):
        result=self.work.review(receipt,principal=self.reviewer)
        self.assertTrue(result["mock_review_completed"])

    def test_one_reviewed_mock_receipt_reaches_ledger_only(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        out=self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)
        self.assertEqual(out["status"],"SYNTHETIC_PROPOSALS_RESERVED_FOR_REVIEW")
        self.assertEqual(out["proposal_count"],1)
        self.assertEqual(out["proposals"][0]["candidate_credit"],"117.00")
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],1)
        self.assertFalse(out["financial_writes"])
        self.assertFalse(out["persistent_ledger"])
        self.assertFalse(out["production_approved"])

    def test_review_before_proposal_is_mandatory(self):
        rid,_,_,ctx=self.create()
        with self.assertRaisesRegex(Stage3MockBlocked,"MOCK_RECEIPT_NOT_REVIEWED"):
            self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],0)

    def test_uploader_cannot_propose_or_review(self):
        rid,_,_,ctx=self.create()
        with self.assertRaises(Exception):
            self.work.review(rid,principal=self.uploader)
        self.review(rid)
        with self.assertRaisesRegex(Stage3MockBlocked,"MOCK_REVIEWER_REQUIRED"):
            self.work.propose(rid,[fake_invoice()],[ctx],principal=self.uploader)

    def test_source_copy_is_immutable_against_caller_mutation(self):
        rid,row,meta,ctx=self.create()
        row["Credit Amount"] = "999.00"
        meta["bank_reference"] = "SYNTH-UTR-EVIL"
        self.review(rid)
        out=self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)
        self.assertEqual(out["proposals"][0]["candidate_credit"],"117.00")

    def test_sidecar_and_context_utr_conflict_denied(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        ctx["bank_reference"]="SYNTH-UTR-OTHER"
        with self.assertRaisesRegex(Stage3MockBlocked,"UTR_SIDECAR_CONTEXT_CONFLICT"):
            self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)

    def test_external_nonfabricated_context_denied(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        ctx["client_name"]="STATE BANK OF INDIA"
        with self.assertRaisesRegex(Stage3MockBlocked,"NONFABRICATED_CLIENT_CONTEXT_FORBIDDEN"):
            self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)

    def test_real_invoice_source_denied(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        inv=fake_invoice();inv["source_kind"]="REAL"
        with self.assertRaisesRegex(Stage3MockBlocked,"ONLY_FABRICATED_INVOICES_ALLOWED"):
            self.work.propose(rid,[inv],[ctx],principal=self.reviewer)

    def test_same_receipt_idempotent_mock_reservation(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)
        result=self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)
        self.assertEqual(result["status"],"MOCK_PROPOSAL_BATCH_ALREADY_RESERVED")
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],1)

    def test_duplicate_utr_across_receipts_rejected(self):
        rid,_,_,ctx=self.create()
        row,sidecar,_=mock_pair("A")
        row["Description"]="SYNTH-CHANGED POSTAGE NOVEMBER 2026"
        sidecar["evidence_row_sha256"]=evidence_row_sha256(row)
        out=self.work.stage([row],[sidecar],principal=self.uploader)
        self.assertFalse(out["mock_receipt_created"])
        self.assertFalse(out["financial_writes"])

    def test_overallocate_across_two_reviewed_receipts_atomic_rollback(self):
        first,_,_,ctx1=self.create("B", "80.00")
        self.review(first)
        self.assertEqual(self.work.propose(first,[fake_invoice()],[ctx1],principal=self.reviewer)["proposal_count"],1)
        second,_,_,ctx2=self.create("C", "50.00")
        self.review(second)
        result=self.work.propose(second,[fake_invoice()],[ctx2],principal=self.reviewer)
        self.assertEqual(result["status"],"MOCK_GLOBAL_OVERALLOCATION_HELD")
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],1)

    def test_two_reviewed_partial_receipts_conserve_invoice_amount(self):
        first,_,_,ctx1=self.create("B", "80.00")
        self.review(first)
        self.work.propose(first,[fake_invoice()],[ctx1],principal=self.reviewer)
        second,_,_,ctx2=self.create("C", "37.00")
        self.review(second)
        result=self.work.propose(second,[fake_invoice()],[ctx2],principal=self.reviewer)
        self.assertEqual(result["status"],"SYNTHETIC_PROPOSALS_RESERVED_FOR_REVIEW")
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],2)

    def test_invoice_value_conflict_after_reserved_prevents_second_receipt(self):
        first,_,_,ctx1=self.create("B", "80.00")
        self.review(first)
        self.work.propose(first,[fake_invoice()],[ctx1],principal=self.reviewer)
        second,_,_,ctx2=self.create("C", "37.00")
        self.review(second)
        inv=fake_invoice();inv["taxable"]="200.00";inv["gross"]="218.00"
        result=self.work.propose(second,[inv],[ctx2],principal=self.reviewer)
        self.assertEqual(result["status"],"MOCK_INVOICE_SOURCE_CONFLICT_HELD")

    def test_pre_activation_payment_rejected_before_reservation(self):
        row,meta,ctx=mock_pair("EARLY")
        meta["bank_date"]="2026-11-20"
        result=self.work.stage([row],[meta],principal=self.uploader)
        self.assertFalse(result["mock_receipt_created"])
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],0)

    def test_wrong_original_credit_lineage_rejected(self):
        row,meta,ctx=mock_pair("WRONG")
        meta["source_credit_column"]="PAYMNENT!H"
        result=self.work.stage([row],[meta],principal=self.uploader)
        self.assertFalse(result["mock_receipt_created"])

    def test_receipt_can_be_reviewed_only_once(self):
        rid,_,_,_=self.create()
        self.review(rid)
        with self.assertRaises(Exception):
            self.work.review(rid,principal=self.reviewer)

    def test_invoice_original_paid_marker_held_no_mock_reservation(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        inv=fake_invoice();inv["original_paid_marker"]=0
        out=self.work.propose(rid,[inv],[ctx],principal=self.reviewer)
        self.assertEqual(out["status"],"MOCK_BATCH_HELD_NO_CANDIDATE_LEDGER_UPDATE")
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],0)

    def test_concurrent_duplicate_batch_proposals_idempotent(self):
        rid,_,_,ctx=self.create()
        self.review(rid)
        results=[]
        def worker():
            results.append(self.work.propose(rid,[fake_invoice()],[ctx],principal=self.reviewer)["status"])
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for th in threads: th.start()
        for th in threads: th.join()
        self.assertEqual(set(results), {"MOCK_PROPOSAL_BATCH_ALREADY_RESERVED",
                                        "SYNTHETIC_PROPOSALS_RESERVED_FOR_REVIEW"})
        self.assertEqual(self.work.counts(principal=self.reviewer)["mock_candidate_edges"],1)

if __name__=="__main__":
    unittest.main()