"""Unit contract checks for partial rows and durable outbox (no AWS)."""
import io
import sqlite3
import os
import sys
import tempfile
import types
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

sys.modules.setdefault('flask',types.SimpleNamespace(jsonify=None,request=None,g=None))
sys.path.insert(0,str(Path(__file__).parent))
from sbi_payment_pg_bridge import _all_source_rows, classify_payment_rows, ContractError
from sbi_pg_outbox import queue_delivery, process_queued, process_pending, recover_missing_receipts, _connect
from sbi_payment_pg_bridge import QA_DATABASE,QA_HOST,QA_WRITER


def make_excel(records):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    def row(number,values):
        return '<row r="%d">'%number+''.join(
            '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'%(chr(65+j),number,escape(str(v)))
            for j,v in enumerate(values))+'</row>'
    data='<worksheet xmlns="'+ns+'"><sheetData>'+row(1,['Description','SOL ID','Credit Amount'])+''.join(row(i+2, r) for i,r in enumerate(records))+'</sheetData></worksheet>'
    workbook=f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for p,s in {'[Content_Types].xml':'<Types/>','xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':rels,'xl/worksheets/sheet1.xml':data}.items():z.writestr(p,s)
    return out.getvalue()


def original_like(payload):
    raw=_all_source_rows(payload)
    valid=[]
    for number,row,reason in raw:
        if reason or not row['Description'].strip():continue
        try:
            money=Decimal(row['Credit Amount'])
            if not money.is_finite() or money<=0 or money*100 != (money*100).to_integral_value():continue
            valid.append(money)
        except Exception:pass
    return {'source_rows':len(raw),'valid_rows':len(valid),'review_rows':len(raw)-len(valid),'valid_credit_total':sum(valid,Decimal('0'))}


class PaymentPartialTests(unittest.TestCase):
    def test_all_valid(self):
        x=make_excel([('OK 1','0123','100.01'),('OK 2','0123','50.99')])
        rows,flags=classify_payment_rows(x,original_like)
        self.assertEqual([r[0] for r in rows],[2,3]);self.assertEqual(flags,[])
        self.assertEqual(sum(r[2] for r in rows),15100)
    def test_partial_invalid_only(self):
        x=make_excel([('OK 1','0123','100.01'),('BAD','0123','0'),('OK 2','0123','50.99')])
        rows,flags=classify_payment_rows(x,original_like)
        self.assertEqual([r[0] for r in rows],[2,4]);self.assertEqual([r['source_row'] for r in flags],[3])
    def test_original_count_conflict_fails_closed(self):
        x=make_excel([('OK','0123','118.00'),('BAD','0123','0')])
        def mismatch(blob):
            p=original_like(blob)
            if p['source_rows']>1:p['valid_rows']=2;p['review_rows']=0
            return p
        with self.assertRaises(ContractError): classify_payment_rows(x,mismatch)
    def test_original_amount_conflict_fails_closed(self):
        x=make_excel([('OK','0123','118.00'),('BAD','0123','0')])
        def mismatch(blob):
            p=original_like(blob)
            if p['source_rows']>1:p['valid_credit_total']=Decimal('119.00')
            return p
        with self.assertRaises(ContractError): classify_payment_rows(x,mismatch)
    def test_only_invalid_rows(self):
        x=make_excel([('BAD','0123','0')])
        rows,review=classify_payment_rows(x,original_like)
        self.assertEqual(rows,[]);self.assertEqual(len(review),1)


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        path=Path(self.temp.name);path.chmod(0o700)
        self.patch=patch.dict(os.environ,{
            'SBI_PG_PAYMENT_BRIDGE_ENABLED':'staging-only',
            'PGHOST':QA_HOST,'PGDATABASE':QA_DATABASE,'PGUSER':QA_WRITER,
            'SBI_PAYMENT_EVIDENCE_DIR':str(path),
            'SBI_PG_OUTBOX_ALLOW_TMPFS':'unit-test-only'
        });self.patch.start()
    def tearDown(self):
        self.patch.stop();self.temp.cleanup()
    def test_durable_retry_and_replay(self):
        data=make_excel([('OK','0123','118.00')]);uid='qa-user'
        import hashlib
        digest=hashlib.sha256(data).hexdigest()
        self.assertEqual(queue_delivery(data,uid),digest)
        self.assertEqual(queue_delivery(data,uid),digest)
        calls=[]
        def fail(payload):
            calls.append(1)
            if len(calls)==1:raise RuntimeError('synthetic pg unavailable')
            return 'COMMITTED'
        with self.assertRaises(RuntimeError): process_queued(digest,uid,fail,lambda d:[])
        self.assertEqual(process_queued(digest,uid,fail,lambda d:[]),'COMMITTED')
        self.assertEqual(process_queued(digest,uid,fail,lambda d:[]),'ALREADY_RECORDED')
        self.assertEqual(len(calls),2)
        with _connect() as db:
            row=db.execute('SELECT state,length(payload),attempt_count FROM delivery_queue').fetchone()
        self.assertEqual(row,('COMMITTED',None,2))
    def test_receipt_recovery_after_crash_window(self):
        import hashlib
        data=make_excel([('OK','0123','118.00')]);digest=hashlib.sha256(data).hexdigest()
        root=Path(os.environ['SBI_PAYMENT_EVIDENCE_DIR'])
        receipt='a'*32
        (root/(receipt+'.xlsx')).write_bytes(data)
        with sqlite3.connect(str(root/'receipts.sqlite3')) as con:
            con.execute('CREATE TABLE receipts(id TEXT,owner_uid TEXT,sha256 TEXT,created_utc TEXT)')
            con.execute('INSERT INTO receipts VALUES (?,?,?,?)',(receipt,'qa-recovery',digest,'2026-11-24T00:00:00Z'))
        self.assertEqual(recover_missing_receipts(),1)
        self.assertEqual(recover_missing_receipts(),0)
        self.assertEqual(process_queued(digest,'qa-recovery',lambda x:'COMMITTED',lambda x:[]),'COMMITTED')

    def test_staging_target_is_enforced(self):
        with patch.dict(os.environ,{'PGDATABASE':'sbi_reconciliation_main'}):
            with self.assertRaises(RuntimeError):queue_delivery(b'test12345678','qa')
    def test_review_is_retained(self):
        data=make_excel([('BAD','0123','0')]);uid='qa2'
        digest=queue_delivery(data,uid)
        self.assertEqual(process_queued(digest,uid,lambda x:'NO_ELIGIBLE_ROWS',lambda x:[{'source_row':2,'reason':'bad'}]),'NO_ELIGIBLE_ROWS')
        with _connect() as db:
            row=db.execute('SELECT state,review_json FROM delivery_queue').fetchone()
        self.assertEqual(row[0],'NO_ELIGIBLE_ROWS')
        self.assertEqual(__import__('json').loads(row[1])[0]['source_row'],2)


if __name__=='__main__':unittest.main(verbosity=2)
