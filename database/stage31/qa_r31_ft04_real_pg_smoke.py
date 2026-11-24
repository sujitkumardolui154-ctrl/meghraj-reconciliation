"""Real isolated PostgreSQL QA, synthetic XLSX, exact FT-04 parser + R31 parser.

RUN ONLY on disposable QA docker with separate privilege-limited PostgreSQL.
No AWS, no source bank rows, no financial allocations, no production tables.
"""
import io
import json
import os
from pathlib import Path
import sys
from openpyxl import Workbook
import psycopg

root=Path(__file__).resolve().parents[2]
ft04=Path(os.environ["SBI_R31_FT04_PINNED_DIR"])/"integrations/sbi_pg_payment_bridge"
r31=Path(os.environ["SBI_R31_APP_PINNED_DIR"])/"staging/aws_login_v150"
sys.path.insert(0,str(root/"database/stage31"))
sys.path.insert(0,str(ft04))
sys.path.insert(0,str(r31))
sys.path.insert(0,str(Path(os.environ["SBI_R31_APP_PINNED_DIR"])/"dashboard_source"))

from db_r31_ft04_ingest_qa import (
    build_receipt_plan,write_qa_source_receipt,
    QA_DB,QA_ROLE,STATUS_PASS,STATUS_MASTER,STATUS_DUP,STATUS_BAD,
    IngestReviewRequired,
)
from sbi_payment_pg_bridge import _all_source_rows
import sbi_payment_pg_bridge as ft04_pinned
from db_r31_ft04_parser_parity import classify_exact_ft04_rows
from db_r31_private_sol_master import load_approved_sol_file,SCHEMA
from db_r31_pg_sol_report_readonly import sol_summary,payment_details
from payment_evidence_upload import _parse
from tempfile import TemporaryDirectory
from hashlib import sha256

def classify_payment_rows(payload,original_parser):
    return classify_exact_ft04_rows(payload,original_parser,ft04_pinned)


def xlsx(rows):
    book=Workbook()
    sheet=book.active
    sheet.title="PAYMENT EVIDENCE"
    sheet.append(("Description","SOL ID","Credit Amount"))
    for row in rows:
        sheet.append(tuple(str(x) for x in row))
    data=io.BytesIO()
    book.save(data)
    book.close()
    return data.getvalue()


def plan(payload, receipt, owner="synthetic-owner-001"):
    # Every owner-facing branch result comes from a REAL private SHA-pinned
    # master-file loader; only SYNTHETIC names and IDs are in CI.
    document={"schema":SCHEMA,"branches":[{
        "sol_id":"001505","official_branch_name":"SOUTHERN AVENUE",
        "approved":True
    }]}
    raw=json.dumps(document,sort_keys=True).encode()
    with TemporaryDirectory() as directory:
        source=Path(directory)/"private-sol-master.json"
        source.write_bytes(raw)
        source.chmod(0o600)
        selected,source_digest=load_approved_sol_file(str(source),
                                                      sha256(raw).hexdigest())
    return build_receipt_plan(
        payload,_parse,_all_source_rows,classify_payment_rows,
        owner_uid=owner,receipt_id=receipt,
        source_sheet_name="PAYMENT EVIDENCE",
        approved_sol_by_key=selected,
        master_sha256=source_digest,
        filename="synthetic-no-bank-data.xlsx",
    )


def totals(connection):
    with connection.cursor() as cur:
        cur.execute("""
          SELECT (SELECT count(*) FROM sbi.import_batches),
                 (SELECT count(*) FROM sbi.payment_source_rows),
                 (SELECT count(*) FROM sbi.payments),
                 (SELECT count(*) FROM sbi.payment_source_status_v1),
                 (SELECT coalesce(sum(credit_paise),0) FROM sbi.payments),
                 (SELECT count(*) FROM sbi.payment_received_source_v1)
        """)
        return tuple(cur.fetchone())


def run():
    assert os.environ.get("SBI_R31_CI_MODE")=="SYNTHETIC_DOCKER_ONLY"
    assert os.environ.get("PGDATABASE")==QA_DB
    assert os.environ.get("PGUSER")==QA_ROLE
    conn=psycopg.connect(os.environ["SBI_R31_QA_DSN"],autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            assert tuple(cur.fetchone())==(QA_DB,QA_ROLE)
            cur.execute("SELECT to_regclass('sbi.payment_received_source_v1') IS NOT NULL")
            assert cur.fetchone()[0] is True
            cur.execute("""SELECT has_table_privilege(current_user,'sbi.payments','UPDATE'),
                                  has_table_privilege(current_user,'sbi.payments','DELETE')""")
            assert tuple(cur.fetchone())==(False,False)
        assert totals(conn)==(0,0,0,0,0,0)

        first=xlsx([
            ("BANK POSTAGE AUG-26","001505","100.00"),
            ("BANK POSTAGE SEP-26","99922","20.00"),
            ("INVALID CREDIT","001505","-1.00"),
            ("REPEATED CANDIDATE","001505","10.00"),
            ("REPEATED CANDIDATE","001505","10.00"),
        ])
        candidate=plan(first,"a"*32)
        assert len(candidate.rows)==5
        assert [r.status for r in candidate.rows]==[
            STATUS_PASS,STATUS_MASTER,STATUS_BAD,STATUS_DUP,STATUS_BAD]
        assert candidate.accepted_credit_paise==13000
        result=write_qa_source_receipt(conn,candidate)
        assert result["status"]=="QA_SOURCE_ROWS_COMMITTED"
        assert result["production_writes"] is False
        assert totals(conn)==(1,5,3,5,13000,5)
        print("DB_R31_FT04_QA_REAL_PG_MIXED_ROW_PARITY=PASS")

        replay=write_qa_source_receipt(conn,candidate)
        assert replay["status"]=="QA_ALREADY_RECORDED"
        assert totals(conn)==(1,5,3,5,13000,5)
        print("DB_R31_FT04_QA_REAL_PG_REPLAY_IDEMPOTENT=PASS")

        different_owner=plan(first,"b"*32,"different-owner")
        try:
            write_qa_source_receipt(conn,different_owner)
            raise AssertionError("same SHA cross owner incorrectly accepted")
        except IngestReviewRequired as e:
            assert str(e)=="GLOBAL_SHA_CROSS_OWNER_REVIEW_REQUIRED"
        assert totals(conn)==(1,5,3,5,13000,5)
        print("DB_R31_FT04_QA_GLOBAL_SHA_CROSS_OWNER=HELD_SAFE")

        second=xlsx([
            ("BANK POSTAGE AUG-26","001505","100.00"),
            ("NEW SEPARATE PAYMENT","001505","7.00"),
        ])
        fresh=plan(second,"c"*32)
        delivered=write_qa_source_receipt(conn,fresh)
        assert delivered["status"]=="QA_SOURCE_ROWS_COMMITTED"
        assert totals(conn)==(2,7,5,7,23700,7)
        with conn.cursor() as cur:
            cur.execute("""SELECT st.source_status,st.reason_codes
                           FROM sbi.payment_source_status_v1 st
                           JOIN sbi.payment_source_rows r ON r.id=st.source_row_id
                           JOIN sbi.import_batches b ON b.id=r.batch_id
                           WHERE b.source_sha256=%s AND r.source_row_number=2""",
                        (fresh.file_sha256,))
            state,reasons=cur.fetchone()
            assert state==STATUS_DUP
            assert reasons==["CROSS_RECEIPT_DUPLICATE_CANDIDATE"]
            cur.execute("""SELECT count(*) FROM sbi.payment_received_source_v1
                           WHERE owner_uid=%s""",("different-owner",))
            assert cur.fetchone()[0]==0
        print("DB_R31_FT04_QA_CROSS_RECEIPT_DUPLICATE_HELD=PASS")
        print("DB_R31_FT04_QA_READONLY_VIEW_SOURCE_ROW_PARITY=PASS")
        # Independent dedicated QA report role: SELECT on the versioned
        # source-only view, NO direct financial table SELECT or DML.
        reporter=psycopg.connect(os.environ["SBI_R31_REPORT_DSN"],autocommit=True)
        try:
            report=sol_summary(reporter,trusted_owner_uid="synthetic-owner-001")
            sol={str(x["sol_id"]):x for x in report["records"]}
            assert set(sol)=={"1505","99922"}
            assert sol["1505"]["payment_rows"]==6
            assert sol["1505"]["valid_payment_rows"]==4
            assert sol["1505"]["credit_paise"]==21700
            assert sol["1505"]["excluded"]==2
            assert sol["1505"]["held_for_review"]==2
            assert sol["1505"]["not_calculated"]==4
            assert sol["1505"]["branch_name"]=="SOUTHERN AVENUE"
            assert sol["99922"]["payment_rows"]==1
            assert sol["99922"]["credit_paise"]==2000
            assert sol["99922"]["branch_name"]=="PENDING_SOL_MASTER_REVIEW"
            assert report["page_totals"]["payment_rows"]==7
            assert report["page_totals"]["credit_paise"]==23700
            assert report["page_totals"]["matched"] is None
            detail=payment_details(reporter,trusted_owner_uid="synthetic-owner-001")
            assert len(detail["records"])==7
            assert len(payment_details(reporter,trusted_owner_uid="different-owner")["records"])==0
            with reporter.cursor() as cur:
                cur.execute("""SELECT has_table_privilege(
                    current_user,'sbi.payments','INSERT'),
                  has_table_privilege(current_user,'sbi.payments','UPDATE'),
                  has_table_privilege(current_user,'sbi.payments','DELETE')""")
                assert tuple(cur.fetchone())==(False,False,False)
            print("DB_R31_QA_READONLY_CANONICAL_SOL_TALLY=PASS")
            print("DB_R31_QA_READONLY_REPORT_OWNER_ISOLATION=PASS")
            print("DB_R31_QA_READONLY_ROLE_FINANCE_DML=DENIED")
        finally:
            reporter.close()
        print("DB_R31_FT04_QA_FINANCIAL_ALLOCATIONS=0")
        print("DB_R31_FT04_QA_PRODUCTION_DATABASE_WRITES=0")
        print("DB_R31_FT04_QA_RELEASE_STATUS=ISOLATED_DOCKER_ONLY")
    finally:
        conn.close()


if __name__=="__main__":
    run()
