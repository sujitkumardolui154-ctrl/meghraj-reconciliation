"""DB-R31.6 private Firebase-session / CSRF staging integration.

This Blueprint is OFF by default and must be registered ONLY in the separately
staged Docker image. It cannot target the production PostgreSQL instance.
The existing /api/payment-evidence/upload route remains the source of immutable
private receipts. This adds a separate authenticated QA sync/reports path.
No allocation, invoice matching, UTR/date inference or production writes.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
import hashlib
import os
from pathlib import Path
import re
import stat

from flask import Blueprint, Response, g, jsonify, request
from openpyxl import load_workbook
from dashboard_sessions import csrf_valid
from payment_evidence_upload import (
    RECEIPT_RE, _connection, _parse, _store,
    _norm_description, _norm_sol, _norm_credit,
)
from payment_received_ledger import load_private_master
from r31_db_r31_owner_source_adapter import (
    QA_DB, QA_USER, authenticated_owner, build_plan, SourceContractError,
    exact_paise, persist_qa_source,
)
from r31_db_r31_owner_report_adapter import (
    QA_REPORT_ROLE, sol_summary, payment_details,
)
from r31_currency import group_to_public, detail_to_public, public_csv

stage_r31 = Blueprint("sbi_r31_isolated_qa", __name__)
PREFIX="/api/r31-private-qa"
ENABLE_VALUE="isolated-ownerqa-firebase-csrf-v1"

# These two private files are mounted *only* in the isolated staging image.
# Never source credentials from posted JSON or client-controlled headers.
CREDENTIALS={
    "ingest":("/run/secrets/r31-ingest.env",QA_USER),
    "report":("/run/secrets/r31-report.env",QA_REPORT_ROLE),
}


class StageBlocked(RuntimeError):
    pass


def _enabled():
    if os.environ.get("SBI_R31_PRIVATE_STAGING_ENABLED")!=ENABLE_VALUE:
        raise StageBlocked("R31_PRIVATE_QA_NOT_ENABLED")


def _credentials(kind):
    filename,role=CREDENTIALS[kind]
    p=Path(filename)
    if not p.is_file() or p.is_symlink():
        raise StageBlocked("R31_PRIVATE_QA_ROLE_SECRET_UNAVAILABLE")
    st=p.stat()
    if (st.st_uid!=os.geteuid() or stat.S_IMODE(st.st_mode)!=0o600
            or st.st_size<50 or st.st_size>1024):
        raise StageBlocked("R31_PRIVATE_QA_ROLE_SECRET_PERMISSIONS")
    result={}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.count("=")!=1:
            raise StageBlocked("R31_PRIVATE_QA_SECRET_FORMAT")
        k,v=line.split("=",1)
        if k not in {"PGHOST","PGPORT","PGDATABASE","PGUSER","PGPASSWORD"} or k in result:
            raise StageBlocked("R31_PRIVATE_QA_SECRET_FIELDS")
        result[k]=v
    expected={
        "PGHOST":"sbi-synthetic-postgres-38-31",
        "PGPORT":"5432",
        "PGDATABASE":QA_DB,
        "PGUSER":role,
    }
    if any(result.get(k)!=v for k,v in expected.items()) or not result.get("PGPASSWORD"):
        raise StageBlocked("R31_PRIVATE_QA_DB_IDENTITY_MISMATCH")
    return result


def _connect(kind):
    import psycopg
    e=_credentials(kind)
    return psycopg.connect(host=e["PGHOST"],port=int(e["PGPORT"]),
                           dbname=e["PGDATABASE"],user=e["PGUSER"],
                           password=e["PGPASSWORD"],connect_timeout=5)


def _valid_user():
    # Existing install_sessions(app) verifies Firebase session cookies,
    # revocation and account claims in before_request; no UID from JSON.
    return authenticated_owner(g.dil_user)


def _verified_private_receipt(owner,receipt_id):
    if not RECEIPT_RE.fullmatch(receipt_id):
        raise SourceContractError("RECEIPT_ID_INVALID")
    base=_store()
    with closing(_connection(base)) as conn:
        row=conn.execute(
            "SELECT * FROM receipts WHERE id=? AND owner_uid=?",
            (receipt_id,owner)).fetchone()
    if row is None:
        raise FileNotFoundError("R31_PRIVATE_RECEIPT_NOT_FOUND")
    if row["filename"] != receipt_id+".xlsx":
        raise StageBlocked("R31_PRIVATE_RECEIPT_LINEAGE_INVALID")
    file=base/row["filename"]
    if not file.is_file() or file.is_symlink() or file.stat().st_size>8*1024*1024:
        raise StageBlocked("R31_PRIVATE_EVIDENCE_FILE_UNSAFE")
    raw=file.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row["sha256"]:
        raise StageBlocked("R31_PRIVATE_SOURCE_SHA_MISMATCH")
    parsed=_parse(raw)
    for col,field in (
        ("source_rows","source_rows"),
        ("valid_rows","valid_rows"),
        ("review_rows","review_rows"),
        ("valid_credit_total","credit_total"),
    ):
        if parsed[col]!=row[field]:
            raise StageBlocked("R31_PRIVATE_RECEIPT_SUMMARY_MISMATCH")
    return raw,parsed,row["source_name"]


def _extract_original_source(raw,parsed):
    wb=load_workbook(BytesIO(raw),read_only=True,data_only=False,keep_links=False)
    rows=[]
    eligible=[]
    review=[]
    seen=set()
    valid_n=review_n=0
    total_paise=0
    try:
        sheet=wb["PAYMENT EVIDENCE"] if "PAYMENT EVIDENCE" in wb else wb.active
        sheet_name=sheet.title
        for number,cells in enumerate(sheet.iter_rows(min_row=2,max_col=4),start=2):
            if all(c.value in (None,"") for c in cells):
                continue
            desc,fa=_norm_description(cells[0])
            sol,fb=_norm_sol(cells[1])
            amount,fc=_norm_credit(cells[2])
            flags=list(fa+fb+fc)
            if cells[3].value not in (None,""):
                flags.append("EXTRA_COLUMN_NOT_ALLOWED")
            key=(desc,sol,amount)
            if key in seen:
                flags.append("REPEATED_SOURCE_ROW_REVIEW")
            else:
                seen.add(key)
            # The immutable .xlsx is the source of truth; JSON text preserves
            # source cell values (Excel displays/format remain in the file).
            original={
                "Description":"" if cells[0].value is None else str(cells[0].value),
                "SOL ID":"" if cells[1].value is None else str(cells[1].value),
                "Credit Amount":"" if cells[2].value is None else str(cells[2].value),
            }
            reason="|".join(sorted(set(flags))) if flags else None
            rows.append((number,original,reason))
            if flags:
                review_n+=1
                review.append({"source_row":number,"reason":reason})
            else:
                # Strict QA contract rejects a source amount that cannot be
                # independently verified to exact paise; never silently round.
                paise=exact_paise(original["Credit Amount"])
                if paise!=int(Decimal(amount)*100):
                    raise StageBlocked("R31_EXACT_SOURCE_AMOUNT_MISMATCH")
                eligible.append((number,original,paise))
                valid_n+=1
                total_paise+=paise
    finally:
        wb.close()
    if (len(rows)!=parsed["source_rows"]
        or valid_n!=parsed["valid_rows"]
        or review_n!=parsed["review_rows"]
        or total_paise!=int(Decimal(parsed["valid_credit_total"])*100)):
        raise StageBlocked("R31_ORIGINAL_PARSER_PARITY_FAILURE")
    return sheet_name,rows,eligible,review


def _plan_for_saved_receipt(owner,receipt_id):
    raw,parsed,original_name=_verified_private_receipt(owner,receipt_id)
    sheet_name,rows,eligible,review=_extract_original_source(raw,parsed)
    selected,state,digest=load_private_master()
    def verified_lookup(sol):
        if sol not in selected or not digest:
            return None
        return (selected[sol],digest)
    return build_plan(
        trusted_owner=owner,trusted_receipt_id=receipt_id,
        original_file_name=original_name,source_sheet_name=sheet_name,
        raw_file=raw,all_source_rows=rows,parser_eligible_rows=eligible,
        parser_review_rows=review,approved_master_lookup=verified_lookup,
    )


def _hold_cross_receipt_candidates(cur,plan):
    # Query with existing owner lock held in the SAME DB transaction to avoid
    # concurrently accepting duplicate candidates from separate receipts.
    cur.execute("""SELECT p.description,p.sol_id,p.credit_paise
       FROM sbi.payments p
       JOIN sbi.payment_source_rows r ON r.id=p.source_row_id
       JOIN sbi.import_batches b ON b.id=r.batch_id
       WHERE b.owner_uid=%s AND b.source_sha256<>%s""",
       (plan.owner_uid,plan.source_sha256))
    prior=set(tuple(r) for r in cur.fetchall())
    updated=[]
    for row in plan.rows:
        fingerprint=(
            row.original["Description"],row.original["SOL ID"],row.amount_paise
        )
        if row.amount_paise is not None and fingerprint in prior:
            row=replace(row,status="HOLD_DUPLICATE_CANDIDATE",
                        reasons=tuple(sorted(set(row.reasons+(
                            "CROSS_RECEIPT_DUPLICATE_CANDIDATE",)))))
        updated.append(row)
    return replace(plan,rows=tuple(updated))


def _private_report(kind,limit,offset):
    _enabled()
    user=_valid_user()
    conn=_connect("report")
    try:
        result=(sol_summary if kind=="sol" else payment_details)(
            conn,g.dil_user,limit=limit,offset=offset)
    finally:
        conn.close()
    converter=group_to_public if kind=="sol" else detail_to_public
    return [converter(r) for r in result]


@stage_r31.get(PREFIX+"/status")
def qa_status():
    _enabled()
    _valid_user()
    return jsonify(
        release_status="FIREBASE_PRIVATE_QA_ONLY",
        database=QA_DB,source_only=True,financial_apply_enabled=False,
        matching_engine_connected=False,currency="INR",
        displayed_currency_unit="RUPEES",internal_storage_unit="PAISE",
        production_database_writes=False,
    )


@stage_r31.get(PREFIX+"/sol-report")
def qa_sol_report():
    try:
        rows=_private_report("sol",100,0)
    except Exception:
        return jsonify(error="Private QA SOL report unavailable"),503
    return jsonify(
        report="SOL_WISE_PAYMENT_RECEIVED_SOURCE_ONLY",
        currency="INR",credit_amount_unit="RUPEES",
        groups=rows,reconciliation_status="NOT_CALCULATED",
        production_financial_writes=False,
    )


@stage_r31.get(PREFIX+"/payment-details")
def qa_payment_details():
    try:
        rows=_private_report("detail",100,0)
    except Exception:
        return jsonify(error="Private QA source details unavailable"),503
    return jsonify(rows=rows,currency="INR",
                   reconciliation_status="NOT_CALCULATED",
                   production_financial_writes=False)


@stage_r31.get(PREFIX+"/sol-report.csv")
def qa_sol_csv():
    try:
        rows=_private_report("sol",1000,0)
        data=public_csv(rows)
    except Exception:
        return jsonify(error="Private QA SOL CSV unavailable"),503
    return Response(data,mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":'attachment; filename="R31_QA_SOL_INR.csv"',
                 "Cache-Control":"private, no-store",
                 "X-R31-Source-Only":"NOT_RECONCILED"})


@stage_r31.get(PREFIX+"/payment-details.csv")
def qa_detail_csv():
    try:
        rows=_private_report("detail",1000,0)
        data=public_csv(rows,detail=True)
    except Exception:
        return jsonify(error="Private QA payment CSV unavailable"),503
    return Response(data,mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":'attachment; filename="R31_QA_PAYMENT_INR.csv"',
                 "Cache-Control":"private, no-store",
                 "X-R31-Source-Only":"NOT_RECONCILED"})


@stage_r31.post(PREFIX+"/receipts/<receipt_id>/sync")
def qa_sync_receipt(receipt_id):
    if not csrf_valid():
        return jsonify(error="Same-origin session CSRF check failed",
                       production_financial_writes=False),403
    try:
        _enabled()
        owner=_valid_user()
        plan=_plan_for_saved_receipt(owner,receipt_id)
        conn=_connect("ingest")
        try:
            # Strict serialization per owner. The owner value comes from a
            # Firebase-verified identity, NEVER from query/body.
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (owner,))
                plan=_hold_cross_receipt_candidates(cur,plan)
            result=persist_qa_source(conn,plan)
        finally:
            conn.close()
    except FileNotFoundError:
        return jsonify(error="Private receipt not found"),404
    except (ValueError,SourceContractError):
        return jsonify(error="Source evidence requires review"),422
    except Exception:
        return jsonify(error="Private QA sync unavailable",
                       production_financial_writes=False),503
    return jsonify(
        status=result,source_rows=len(plan.rows),
        amount_unit="RUPEES",source_only=True,
        reconciliation_status="NOT_CALCULATED",
        production_financial_writes=False,
    ),200 if result=="ALREADY_RECORDED" else 201
