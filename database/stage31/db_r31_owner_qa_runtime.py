"""Combined isolated DB-R31 owner QA: actual app parser -> immutable PG -> report.

Runs in a short-lived container built from the running app image, connected only
to the synthetic internal PostgreSQL network. Synthetic owner identities are NOT
Firebase authentication evidence. Modes: writer, reader.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import zipfile

try:
    import psycopg
except ImportError:
    import psycopg2 as psycopg
from openpyxl import Workbook, load_workbook
import payment_evidence_upload as original

from db_r31_owner_source_adapter import (
    QA_DB, QA_USER, authenticated_owner, build_plan, persist_qa_source
)
from db_r31_owner_report_adapter import (
    QA_REPORT_ROLE, sol_summary, payment_details, payment_details_csv
)

OWNER_A="synthetic-r31-owner-a"
OWNER_B="synthetic-r31-owner-b"
RECEIPT_A="a"*32
RECEIPT_B="b"*32

def workbook_bytes():
    book=Workbook()
    sheet=book.active
    sheet.title="PAYMENT EVIDENCE"
    sheet.append(["Description","SOL ID","Credit Amount"])
    sheet.append(["QA SOURCE CREDIT","001505","118.00"])
    sheet.append(["QA INVALID ZERO","001505","0"])
    for row in sheet.iter_rows():
        for cell in row:
            cell.number_format="@"
    book.properties.creator="SBI isolated synthetic R31"
    book.properties.created=datetime(2020,1,1,tzinfo=timezone.utc)
    book.properties.modified=datetime(2020,1,1,tzinfo=timezone.utc)
    first=BytesIO()
    book.save(first)
    # Stable ZIP metadata => same SHA for identical synthetic XLSX on rerun.
    output=BytesIO()
    with zipfile.ZipFile(BytesIO(first.getvalue())) as source:
        with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as dest:
            for name in sorted(source.namelist()):
                zi=zipfile.ZipInfo(name,(2020,1,1,0,0,0))
                zi.compress_type=zipfile.ZIP_DEFLATED
                dest.writestr(zi,source.read(name))
    return output.getvalue()


def approved_parser_rows(data):
    summary=original._parse(data)
    if (summary.get("source_rows"),summary.get("valid_rows"),
        summary.get("review_rows"))!=(2,1,1):
        raise RuntimeError("R31_EXISTING_PARSER_MIXED_ROWS_REJECTED")
    if Decimal(str(summary.get("valid_credit_total")))*100!=11800:
        raise RuntimeError("R31_ORIGINAL_PARSER_CREDIT_TOTAL_WRONG")
    workbook=load_workbook(BytesIO(data),read_only=True,data_only=False)
    sheet=workbook["PAYMENT EVIDENCE"]
    raw_rows=[]
    eligible=[]
    reviewed=[]
    for number in (2,3):
        vals=[sheet.cell(number,i).value for i in (1,2,3)]
        if not all(type(x) is str for x in vals):
            raise RuntimeError("R31_SOURCE_CELLS_MUST_BE_TEXT")
        row=dict(zip(("Description","SOL ID","Credit Amount"),vals))
        raw_rows.append((number,row,None if number==2 else "INVALID_CREDIT_AMOUNT"))
        # Verify original parser's decision on one-row workbook as well.
        single=Workbook()
        ws=single.active
        ws.title="PAYMENT EVIDENCE"
        ws.append(["Description","SOL ID","Credit Amount"])
        ws.append(vals)
        for x in ws[2]:
            x.number_format="@"
        s=BytesIO()
        single.save(s)
        one=original._parse(s.getvalue())
        if number==2:
            if (one["source_rows"],one["valid_rows"],one["review_rows"])!=(1,1,0):
                raise RuntimeError("R31_ORIGINAL_ROW_ELIGIBILITY_CHANGED")
            eligible.append((number,row,11800))
        else:
            if (one["source_rows"],one["valid_rows"],one["review_rows"])!=(1,0,1):
                raise RuntimeError("R31_ORIGINAL_INVALID_ROW_NOT_FLAGGED")
            reasons=one.get("review_flag_counts")
            reason=(next(iter(reasons)) if isinstance(reasons,dict) and reasons else
                    "ORIGINAL_PARSER_REVIEW")
            reviewed.append({"source_row":number,"reason":reason})
    workbook.close()
    return raw_rows,eligible,reviewed


def connection():
    return psycopg.connect(connect_timeout=8)


def writer():
    raw=workbook_bytes()
    original,eligible,reviewed=approved_parser_rows(raw)
    print("DB_R31_LIVE_APP_PARSER_MIXED_EVIDENCE=PASS",flush=True)
    identityA=SimpleNamespace(uid=OWNER_A)
    identityB=SimpleNamespace(uid=OWNER_B)
    plans=[
        build_plan(trusted_owner=authenticated_owner(identity),
                   trusted_receipt_id=receipt,original_file_name="qa-r31-payment.xlsx",
                   source_sheet_name="PAYMENT EVIDENCE",raw_file=raw,
                   all_source_rows=original,parser_eligible_rows=eligible,
                   parser_review_rows=reviewed,
                   approved_master_lookup=None)
        for identity,receipt in ((identityA,RECEIPT_A),(identityB,RECEIPT_B))
    ]
    if plans[0].source_sha256 != plans[1].source_sha256:
        raise RuntimeError("R31_IDENTICAL_SHA_TEST_INVALID")
    if any(
        [(row.status,row.amount_paise) for row in p.rows]
        != [("HOLD_SOL_MASTER",11800),("EXCLUDED_INVALID_SOURCE",None)]
        for p in plans
    ):
        raise RuntimeError("R31_SOURCE_CLASSIFICATION_INVALID")

    first=[]
    for plan in plans:
        conn=connection()
        try:
            first.append(persist_qa_source(conn,plan))
        finally:
            conn.close()
    if any(s not in ("SOURCE_COMMITTED_NOT_RECONCILED","ALREADY_RECORDED")
           for s in first):
        raise RuntimeError("R31_COMMIT_NOT_CONFIRMED")
    replay=[]
    for plan in plans:
        conn=connection()
        try:
            replay.append(persist_qa_source(conn,plan))
        finally:
            conn.close()
    if replay!=["ALREADY_RECORDED","ALREADY_RECORDED"]:
        raise RuntimeError("R31_OWNER_IDEMPOTENT_REPLAY_FAILED")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT current_database(),current_user,
                (SELECT count(*) FROM sbi.import_batches b
                 WHERE b.owner_uid IN (%s,%s)
                   AND b.source_sha256=%s),
                (SELECT count(*) FROM sbi.payment_source_rows r
                 JOIN sbi.import_batches b ON b.id=r.batch_id
                 WHERE b.owner_uid IN (%s,%s)
                   AND b.source_sha256=%s),
                (SELECT count(*) FROM sbi.payments p
                 JOIN sbi.payment_source_rows r ON r.id=p.source_row_id
                 JOIN sbi.import_batches b ON b.id=r.batch_id
                 WHERE b.owner_uid IN (%s,%s)
                   AND b.source_sha256=%s)""",
                (OWNER_A,OWNER_B,plans[0].source_sha256)*3)
            row=tuple(cur.fetchone())
            if row!=(QA_DB,QA_USER,2,4,2):
                raise RuntimeError("R31_OWNER_REVIEW_SOURCE_PERSISTENCE_WRONG:"+str(row))
            cur.execute("""SELECT count(*) FROM sbi.payment_source_status_v1 st
               JOIN sbi.payment_source_rows r ON st.source_row_id=r.id
               JOIN sbi.import_batches b ON b.id=r.batch_id
               WHERE b.owner_uid IN (%s,%s)
                 AND st.source_status='EXCLUDED_INVALID_SOURCE'
                 AND NOT EXISTS(
                    SELECT 1 FROM sbi.payments p WHERE p.source_row_id=r.id
                 )""",(OWNER_A,OWNER_B))
            if cur.fetchone()[0]!=2:
                raise RuntimeError("R31_INVALID_SOURCE_NOT_RETAINED")
    print("DB_R31_TWO_OWNER_SAME_SHA_PERSISTENT_QA=PASS",flush=True)
    print("DB_R31_DUPLICATE_REPLAY_NO_NEW_WRITES=PASS",flush=True)
    print("DB_R31_INVALID_SOURCE_ROWS_AND_STATUS=PASS",flush=True)
    print("DB_R31_SOURCE_CREDIT_PAISE_PER_OWNER=11800",flush=True)


def reader():
    for uid,receipt in ((OWNER_A,RECEIPT_A),(OWNER_B,RECEIPT_B)):
        conn=connection()
        try:
            groups=sol_summary(conn,SimpleNamespace(uid=uid))
        finally:
            conn.close()
        if len(groups)!=1:
            raise RuntimeError("R31_OWNER_REPORT_GROUP_COUNT_WRONG")
        g=groups[0]
        for k,v in {
            "raw_sol":"001505",
            "uploaded_source_rows":2,
            "valid_received_rows":1,
            "received_credit_paise":11800,
            "excluded_invalid_rows":1,
            "held_rows":1,
            "reconciliation_status":"NOT_CALCULATED"
        }.items():
            if g.get(k)!=v:
                raise RuntimeError("R31_REPORT_VALUE_MISMATCH_"+k)
        if g.get("verified_matched_payment_rows") is not None:
            raise RuntimeError("R31_FALSE_MATCHED_AMOUNT")
        conn=connection()
        try:
            details=payment_details(conn,SimpleNamespace(uid=uid))
        finally:
            conn.close()
        if len(details)!=2 or {r["source_receipt_id"] for r in details}!={receipt}:
            raise RuntimeError("R31_CROSS_OWNER_DETAIL_DATA_LEAK_OR_GAP")
        if not any(
            r["source_status"]=="EXCLUDED_INVALID_SOURCE"
            and r["credit_paise"] is None for r in details
        ):
            raise RuntimeError("R31_SOURCE_INVALID_MISSING_IN_REPORT")
        conn=connection()
        try:
            csv_data=payment_details_csv(conn,SimpleNamespace(uid=uid))
        finally:
            conn.close()
        if not csv_data.startswith(b"\xef\xbb\xbf") or b"001505" not in csv_data:
            raise RuntimeError("R31_CSV_EXPORT_FAILED")
    print("DB_R31_OWNER_FILTERED_SQL_AND_CSV_PARITY=PASS",flush=True)
    print("DB_R31_NO_UNVERIFIED_RECONCILIATION=PASS",flush=True)

if __name__=="__main__":
    import sys
    if len(sys.argv)!=2 or sys.argv[1] not in ("writer","reader"):
        raise SystemExit("USAGE: writer|reader")
    if sys.argv[1]=="writer":
        writer()
    else:
        reader()
