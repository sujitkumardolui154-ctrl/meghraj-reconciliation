"""Only invented future invoices/UTRs. No historical workbook or financial connection."""
import hashlib
import hmac
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from stage4_ledger import (NewOnlyCandidateLedger, Principal, Stage4Blocked,
                           Stage4Policy, paise, verify_attestation, upload_row_sha256)

KEY=b"THIS_IS_AN_ENTIRELY_FAKE_STAGE4_SIGNATURE_SECRET_2026"
H=lambda x: hashlib.sha256(x.encode()).hexdigest()
I=Principal("demo_intake", "INTAKE")
R=Principal("demo_reviewer", "REVIEWER")
E=Principal("synthetic_engine", "CANDIDATE_ENGINE")
P=Stage4Policy("SBI_INTERNAL_GATEWAY_TEST", "2026-11-21", "2026-11-22", KEY)

def sign(body,kind="bank"):
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    return hmac.new(KEY,b"SBI_STG4_V1:"+kind.encode()+b":"+raw,hashlib.sha256).hexdigest()

def bank(ref="SYNTH-UTR-0001",credit="118.00",sol="1505",client="DEMO CLIENT",
         invoice="SYNTH-INV-0001",date="2026-11-22",source="test-bank"):
    row={"Description":"SYNTH POSTAGE NOV 2026", "SOL ID":sol, "Credit Amount":credit}
    return dict(schema="SBI_BANK_EVIDENCE_V1",issuer=P.issuer,source_kind="NEW_ONLY",
                upload_row_sha256=upload_row_sha256(row),source_sha256=H(source),source_row=2,source_column="PAYMNENT!I",
                statement_sha256=H("fabricated-statement"),bank_date=date,
                payment_reference=ref,sol_id=sol,client_name=client,
                description="SYNTH POSTAGE NOV 2026",credit_amount=credit,
                invoice_reference=invoice,service_month="2026-11")

def inv(number="SYNTH-INV-0001",gross="236.00",sol="1505",client="DEMO CLIENT",
        date="2026-11-21",source="test-invoice"):
    return dict(schema="SBI_INVOICE_EVIDENCE_V1",issuer=P.issuer,source_kind="NEW_ONLY",
                source_sha256=H(source),source_row=2,invoice_no=number,invoice_date=date,
                sol_id=sol,client_name=client,service_month="2026-11",
                taxable="200.00",cgst="18.00",sgst="18.00",gross=gross,
                paid_marker="",credit_note=False)

class Stage4Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=os.path.join(self.tmp.name,"new_only.sqlite3")
        self.store=NewOnlyCandidateLedger(self.path,P)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def add(self, b=None, i=None, review=True):
        b=b or bank();i=i or inv()
        self.store.record_invoice(i,sign(i,"invoice"),actor=I)
        self.store.record_bank(b,sign(b),actor=I)
        if review:self.store.review_bank(b["payment_reference"],actor=R)
        return b,i
    def deny(self, expected,call):
        with self.assertRaisesRegex(Stage4Blocked,expected):call()

    def test_01_strict_signed_bank_and_invoice_dual_review_and_candidate(self):
        b,i=self.add()
        r=self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],"118.00",engine_review_sha=H("candidate1"),actor=E)
        self.assertEqual(r['status'],'CANDIDATE_RESERVED_NOT_SETTLED')
        s=self.store.status();self.assertFalse(s['financial_writes']);self.assertFalse(s['financial_apply_enabled']);self.assertEqual(s['counts']['reservations'],1)
    def test_02_durable_across_restart(self):
        b,i=self.add();self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],"118.00",engine_review_sha=H("r"),actor=E)
        self.store.close();self.store=NewOnlyCandidateLedger(self.path,P)
        self.assertEqual(self.store.status()['counts']['reservations'],1)
    def test_03_identical_signed_receipt_idempotent(self):
        b=bank();s=sign(b)
        self.store.record_bank(b,s,actor=I)
        self.assertTrue(self.store.record_bank(b,s,actor=I)['idempotent'])
    def test_04_reused_utr_different_amount_blocked(self):
        b=bank();self.store.record_bank(b,sign(b),actor=I)
        other=bank(credit="119.00")
        self.deny('DUPLICATE_UTR',lambda:self.store.record_bank(other,sign(other),actor=I))
    def test_05_wrong_hmac_rejected_before_db(self):
        b=bank()
        self.deny('SIGNATURE_MISMATCH',lambda:self.store.record_bank(b,"0"*64,actor=I))
        self.assertEqual(self.store.status()['counts']['receipts'],0)
    def test_06_tampered_amount_after_sign_rejected(self):
        b=bank();signature=sign(b);b['credit_amount']='999.00'
        self.deny('SIGNATURE_MISMATCH',lambda:self.store.record_bank(b,signature,actor=I))
    def test_07_unsigned_verified_flag_not_allowed(self):
        b=bank();b['source_verified']=True
        self.deny('ATTESTATION_SCHEMA_MISMATCH',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_08_wrong_credit_column_denied(self):
        b=bank();b['source_column']='PAYMNENT!H'
        self.deny('CREDIT_MUST_BE_COLUMN_I',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_09_pre_cutoff_denied(self):
        b=bank(date='2026-11-20')
        self.deny('BANK_DATE_OUTSIDE',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_10_future_bank_date_denied(self):
        b=bank(date='2026-11-23')
        self.deny('BANK_DATE_OUTSIDE',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_11_old_invoice_denied(self):
        i=inv(date='2026-11-20')
        self.deny('INVOICE_DATE_OUTSIDE',lambda:self.store.record_invoice(i,sign(i,'invoice'),actor=I))
    def test_12_paid_marker_including_zero_denied(self):
        i=inv();i['paid_marker']='0'
        self.deny('PAID_OR_CREDIT',lambda:self.store.record_invoice(i,sign(i,'invoice'),actor=I))
    def test_13_credit_note_denied(self):
        i=inv();i['credit_note']=True
        self.deny('PAID_OR_CREDIT',lambda:self.store.record_invoice(i,sign(i,'invoice'),actor=I))
    def test_14_gross_mismatch_denied(self):
        i=inv(gross='200.00')
        self.deny('GROSS_MISMATCH',lambda:self.store.record_invoice(i,sign(i,'invoice'),actor=I))
    def test_15_wrong_role_and_dict_principal_denied(self):
        b=bank()
        self.deny('TRUSTED_PRINCIPAL_ROLE',lambda:self.store.record_bank(b,sign(b),actor=R))
        self.deny('TRUSTED_PRINCIPAL_ROLE',lambda:self.store.record_bank(b,sign(b),actor={'uid':I.uid,'role':I.role}))
    def test_16_self_review_denied(self):
        b=bank();self.store.record_bank(b,sign(b),actor=I)
        self.deny('SELF_REVIEW_DENIED',lambda:self.store.review_bank(b['payment_reference'],actor=Principal(I.uid,'REVIEWER')))
    def test_17_unreviewed_cannot_reserve(self):
        b,i=self.add(review=False)
        self.deny('DUAL_REVIEW_REQUIRED',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'118.00',engine_review_sha=H('r'),actor=E))
    def test_18_invoice_capacity_enforced_across_payment_refs(self):
        i=inv(gross='236.00');self.store.record_invoice(i,sign(i,'invoice'),actor=I)
        for n in (1,2):
            b=bank(ref=f'SYNTH-UTR-{n:04}',credit='118.01',source=f'state{n}')
            self.store.record_bank(b,sign(b),actor=I);self.store.review_bank(b['payment_reference'],actor=R)
        self.store.reserve_candidate('SYNTH-UTR-0001',i['invoice_no'],'118.01',engine_review_sha=H('1'),actor=E)
        self.deny('INVOICE_CAPACITY_OVER_RESERVED',lambda:self.store.reserve_candidate('SYNTH-UTR-0002',i['invoice_no'],'118.01',engine_review_sha=H('2'),actor=E))
        self.assertEqual(self.store.status()['counts']['reservations'],1)
    def test_19_payment_credit_capacity_enforced(self):
        b,i=self.add()
        self.deny('PAYMENT_CREDIT_OVER_RESERVED',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'118.01',engine_review_sha=H('p'),actor=E))
    def test_20_conflicting_repeat_reservation_rejected(self):
        b,i=self.add();args=(b['payment_reference'],i['invoice_no'])
        self.store.reserve_candidate(*args,'118.00',engine_review_sha=H('p'),actor=E)
        self.deny('CONFLICTING_REPEAT',lambda:self.store.reserve_candidate(*args,'117.00',engine_review_sha=H('p2'),actor=E))
    def test_21_idempotent_repeat_reservation(self):
        b,i=self.add();args=(b['payment_reference'],i['invoice_no'])
        self.store.reserve_candidate(*args,'118.00',engine_review_sha=H('p'),actor=E)
        self.assertTrue(self.store.reserve_candidate(*args,'118.00',engine_review_sha=H('p'),actor=E)['idempotent'])
    def test_22_sol_conflict_denied(self):
        b=bank(sol='0001');i=inv(sol='0002');self.add(b,i)
        self.deny('SOL_CLIENT_PERIOD_CONFLICT',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'100.00',engine_review_sha=H('p'),actor=E))
    def test_23_client_conflict_denied(self):
        b=bank(client='TEST CLIENT A');i=inv(client='TEST CLIENT B');self.add(b,i)
        self.deny('SOL_CLIENT_PERIOD_CONFLICT',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'100.00',engine_review_sha=H('p'),actor=E))
    def test_24_wrong_invoice_ref_denied(self):
        b=bank(invoice='SYNTH-INV-OTHER');i=inv();self.add(b,i)
        self.deny('EXACT_INVOICE_REFERENCE',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'100.00',engine_review_sha=H('p'),actor=E))
    def test_25_nonexact_float_and_large_rejected(self):
        for value in (12.3,'1.000','-1.00','1e3','1000000000000.00'):
            with self.subTest(value=value):
                self.deny('STRICT_DECIMAL_STRING_REQUIRED',lambda:paise(value))
    def test_26_invoice_evidence_conflicting_duplicate(self):
        i=inv();self.store.record_invoice(i,sign(i,'invoice'),actor=I)
        other=inv(source='altered-document')
        self.deny('DUPLICATE_INVOICE_WITH_CONFLICTING',lambda:self.store.record_invoice(other,sign(other,'invoice'),actor=I))
    def test_27_wrong_issuer_denied(self):
        b=bank();b['issuer']='UNTRUSTED_GATEWAY'
        self.deny('ISSUER_OR_NEW_ONLY',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_28_wrong_scope_denied(self):
        b=bank();b['source_kind']='HISTORICAL'
        self.deny('ISSUER_OR_NEW_ONLY',lambda:self.store.record_bank(b,sign(b),actor=I))
    def test_29_production_apply_config_denied(self):
        self.deny('PRODUCTION_FINANCE_APPLY_FORBIDDEN',lambda:Stage4Policy(P.issuer,'2026-11-21','2026-11-22',KEY,finance_apply_enabled=True))
    def test_30_missing_secret_denied(self):
        self.deny('SERVER_OWNED_HMAC_SECRET',lambda:Stage4Policy(P.issuer,'2026-11-21','2026-11-22',b'weak'))
    def test_31_no_memory_database_or_missing_parent(self):
        self.deny('EXPLICIT_ISOLATED_SQLITE_FILE',lambda:NewOnlyCandidateLedger(':memory:',P))
        self.deny('DEDICATED_DATABASE_DIRECTORY',lambda:NewOnlyCandidateLedger('/nonexistent/f/new.sqlite3',P))
    def test_32_multiple_process_sqlite_capacity_is_atomic(self):
        i=inv();self.store.record_invoice(i,sign(i,'invoice'),actor=I)
        for n in (1,2):
            b=bank(ref=f'SYNTH-UTR-{n:04}',credit='200.00',source=f'bankstmt{n}')
            self.store.record_bank(b,sign(b),actor=I);self.store.review_bank(b['payment_reference'],actor=R)
        barrier=threading.Barrier(2)
        out=[]
        def worker(n):
            with NewOnlyCandidateLedger(self.path,P) as db:
                barrier.wait()
                try:
                    res=db.reserve_candidate(f'SYNTH-UTR-{n:04}',i['invoice_no'],'200.00',engine_review_sha=H(str(n)),actor=E)
                    out.append(res['status'])
                except Stage4Blocked as exc:out.append(str(exc))
        t1=threading.Thread(target=worker,args=(1,));t2=threading.Thread(target=worker,args=(2,))
        t1.start();t2.start();t1.join(timeout=5);t2.join(timeout=5)
        self.assertFalse(t1.is_alive() or t2.is_alive())
        self.assertEqual(out.count('CANDIDATE_RESERVED_NOT_SETTLED'),1)
        self.assertEqual(out.count('INVOICE_CAPACITY_OVER_RESERVED'),1)
        self.assertEqual(self.store.status()['counts']['reservations'],1)
    def test_33_no_writer_or_paid_status(self):
        s=self.store.status()
        self.assertFalse(s['financial_apply_enabled']);self.assertFalse(s['bank_source_authenticated']);self.assertFalse(s['firebase_authenticated']);self.assertFalse(s['invoice_paid_markers_updated'])
    def test_35_exact_upload_signed_binding(self):
        b=bank();row={"Description":b["description"],"SOL ID":b["sol_id"],"Credit Amount":b["credit_amount"]}
        v=self.store.stage_uploaded_bank(row,b,sign(b),actor=I)
        self.assertEqual(v['status'],'PENDING_REVIEW')
    def test_36_change_uploaded_credit_after_sign_denied(self):
        b=bank();row={"Description":b["description"],"SOL ID":b["sol_id"],"Credit Amount":"119.00"}
        self.deny('SIGNED_UPLOAD_ROW_DIGEST_MISMATCH',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))
    def test_37_change_uploaded_sol_after_sign_denied(self):
        b=bank();row={"Description":b["description"],"SOL ID":"001505","Credit Amount":b["credit_amount"]}
        self.deny('SIGNED_UPLOAD_ROW_DIGEST_MISMATCH',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))
    def test_38_change_uploaded_description_after_sign_denied(self):
        b=bank();row={"Description":"SYNTH ADJUSTMENT", "SOL ID":b["sol_id"],"Credit Amount":b["credit_amount"]}
        self.deny('SIGNED_UPLOAD_ROW_DIGEST_MISMATCH',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))
    def test_39_extra_upload_column_fails_closed(self):
        b=bank();row={"Description":b["description"],"SOL ID":b["sol_id"],"Credit Amount":b["credit_amount"],"Debit":"0.00"}
        self.deny('EXACT_THREE_COLUMN_UPLOAD_REQUIRED',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))
    def test_40_row_digest_tampered_even_if_resigned(self):
        b=bank();b['upload_row_sha256']=H('other-valid-hash')
        row={"Description":b["description"],"SOL ID":b["sol_id"],"Credit Amount":b["credit_amount"]}
        self.deny('SIGNED_UPLOAD_ROW_DIGEST_MISMATCH',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))
    def test_41_malformed_upload_money_denied(self):
        b=bank();row={"Description":b["description"],"SOL ID":b["sol_id"],"Credit Amount":118.0}
        self.deny('STRICT_DECIMAL_STRING_REQUIRED',lambda:self.store.stage_uploaded_bank(row,b,sign(b),actor=I))

    def test_34_service_month_conflict(self):
        b=bank();i=inv();i['service_month']='2026-10';self.add(b,i)
        self.deny('SOL_CLIENT_PERIOD_CONFLICT',lambda:self.store.reserve_candidate(b['payment_reference'],i['invoice_no'],'100.00',engine_review_sha=H('p'),actor=E))

if __name__=='__main__': unittest.main()