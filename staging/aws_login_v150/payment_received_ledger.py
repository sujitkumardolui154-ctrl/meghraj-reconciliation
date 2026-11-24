"""R31: private, append-only PAYMENT RECEIVED EVIDENCE ledger (not settlement).

Each fixed-header three-column workbook row is stored under its immutable
receipt. SOL lookup is automatic ONLY when an operator-provisioned PRIVATE
official SOL master contains one unambiguous approved branch name.
A missing, ambiguous or unverified SOL is retained with a row-specific hold.
The financial allocation engine is NOT called; all amounts are evidence, never
booked receipts. A later fresh invoice run may consume only eligible records.

Original PAYMNENT A:L and Invoice Details S are never loaded or modified.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
import csv
import json
import os
import re
import sqlite3
import stat
from openpyxl import load_workbook

MASTER_SCHEMA="sbi-private-approved-sol-master/v1"
MAX_MASTER_BYTES=2*1024*1024
MAX_MASTER_ROWS=5000
SHA=re.compile(r"[0-9a-f]{64}\Z")
SOL=re.compile(r"[0-9]{1,12}\Z")
STATUS_PENDING="PENDING_RECONCILIATION"
STATUS_MASTER="HOLD_SOL_MASTER"
STATUS_DUPLICATE="HOLD_DUPLICATE_CANDIDATE"
STATUS_EXCLUDED="EXCLUDED_INVALID_SOURCE"
TABLE="payment_received_evidence_v1"
SOURCE_HEADERS=("Description","SOL ID","Credit Amount")


class PaymentLedgerRefusal(ValueError):
    """Fixed public refusal codes, never source/customer details."""


def insist(ok,code):
    if not ok:
        raise PaymentLedgerRefusal(code)


def canonical_sol(value):
    if type(value) is not str or SOL.fullmatch(value) is None:
        return None
    return value.lstrip("0") or None


def load_private_master():
    """Exact SHA-pinned, non-symlink, private JSON; never fallback to a guess.

    The path and expected SHA are provided by operator-controlled runtime env,
    not by an upload or URL. This is a technical integrity check, not a
    requirement for a separate Finance certificate to deploy code.
    """
    name=os.environ.get("SBI_PAYMENT_SOL_MASTER_FILE","")
    digest=os.environ.get("SBI_PAYMENT_SOL_MASTER_SHA256","")
    if not name and not digest:
        return {}, "PRIVATE_SOL_MASTER_NOT_CONFIGURED", None
    insist(bool(name) and type(digest) is str and SHA.fullmatch(digest),
           "PRIVATE_SOL_MASTER_PIN_REQUIRED")
    path=Path(name)
    insist(path.is_absolute() and not path.is_symlink() and
           path.is_file() and not path.parent.is_symlink(),
           "PRIVATE_SOL_MASTER_PATH_UNSAFE")
    st=path.stat()
    insist(st.st_size>0 and st.st_size<=MAX_MASTER_BYTES and
           not bool(stat.S_IMODE(st.st_mode)&0o022),
           "PRIVATE_SOL_MASTER_PERMISSIONS_OR_SIZE")
    raw=path.read_bytes()
    insist(sha256(raw).hexdigest()==digest,"PRIVATE_SOL_MASTER_SHA256_MISMATCH")
    try:
        document=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        raise PaymentLedgerRefusal("PRIVATE_SOL_MASTER_JSON_INVALID") from None
    insist(type(document) is dict and
           document.get("schema")==MASTER_SCHEMA and
           type(document.get("branches")) is list and
           0<len(document["branches"])<=MAX_MASTER_ROWS,
           "PRIVATE_SOL_MASTER_SCHEMA_INVALID")
    grouped=defaultdict(set)
    flagged=set()
    for entry in document["branches"]:
        insist(type(entry) is dict and
               set(entry)=={"sol_id","official_branch_name","approved"},
               "PRIVATE_SOL_MASTER_ROW_SCHEMA_INVALID")
        sol=canonical_sol(entry["sol_id"])
        name=entry["official_branch_name"]
        insist(sol is not None and type(name) is str and
               bool(name.strip()) and len(name)<=180 and
               type(entry["approved"]) is bool,
               "PRIVATE_SOL_MASTER_ROW_INVALID")
        # Even unapproved identities must prevent silent auto-approval.
        if entry["approved"]:
            grouped[sol].add(name.strip())
        else:
            flagged.add(sol)
    selected={}
    for sol,names in grouped.items():
        if len(names)==1 and sol not in flagged:
            selected[sol]=next(iter(names))
    contested=flagged|{k for k,v in grouped.items() if len(v)!=1}
    return selected, "MASTER_LOADED", digest


def ensure_payment_schema(conn):
    # Only new tables; no ALTER of original invoice or finance tables.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
          owner_uid TEXT NOT NULL,
          receipt_id TEXT NOT NULL,
          excel_row INTEGER NOT NULL CHECK (excel_row>=2),
          source_sha256 TEXT NOT NULL,
          description TEXT NOT NULL,
          sol_id_text TEXT NOT NULL,
          canonical_sol TEXT NOT NULL,
          official_branch_name TEXT NOT NULL,
          credit_amount TEXT NOT NULL,
          review_reasons_json TEXT NOT NULL,
          source_status TEXT NOT NULL
            CHECK (source_status IN (
                'PENDING_RECONCILIATION','HOLD_SOL_MASTER',
                'HOLD_DUPLICATE_CANDIDATE','EXCLUDED_INVALID_SOURCE')),
          sol_master_sha256 TEXT,
          created_utc TEXT NOT NULL,
          PRIMARY KEY (owner_uid,receipt_id,excel_row)
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS ix_r31_payment_sol "
                 f"ON {TABLE}(owner_uid,canonical_sol,source_status)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS ix_r31_payment_receipt "
                 f"ON {TABLE}(owner_uid,receipt_id,excel_row)")
    # Explicit versioned match evidence table reserved for future *verified*
    # engine integration. R31 never inserts, updates or populates it.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payment_reconciliation_verified_v1 (
          owner_uid TEXT NOT NULL,
          receipt_id TEXT NOT NULL,
          excel_row INTEGER NOT NULL,
          verified_invoice_no TEXT NOT NULL,
          matching_method TEXT NOT NULL,
          payment_portion TEXT NOT NULL,
          verified_evidence_ref TEXT NOT NULL,
          verified_at_utc TEXT NOT NULL,
          PRIMARY KEY(owner_uid,receipt_id,excel_row,verified_invoice_no)
        )
    """)


def append_receipt(conn, *, owner_uid, receipt_id, source_sha256,
                   source_bytes, original_parsed, created_utc):
    """Persist all source rows in the same transaction as the receipt.

    Invalid rows are recorded with explicit exclusions but never passed to the
    future engine. Source contents are never overwritten or deleted.
    """
    insist(type(source_bytes) is bytes and
           sha256(source_bytes).hexdigest()==source_sha256,
           "PAYMENT_SOURCE_HASH_CHANGED")
    insist(type(owner_uid) is str and bool(owner_uid) and
           re.fullmatch(r"[a-f0-9]{32}",receipt_id) is not None and
           SHA.fullmatch(source_sha256) is not None,
           "PAYMENT_RECEIPT_IDENTITY_INVALID")
    selected,master_state,master_digest=load_private_master()
    from payment_evidence_upload import (
        _norm_description,_norm_sol,_norm_credit,
    )
    try:
        wb=load_workbook(BytesIO(source_bytes),read_only=True,
                         data_only=False,keep_links=False)
    except Exception:
        raise PaymentLedgerRefusal("PAYMENT_SOURCE_XLSX_UNREADABLE") from None
    observed=0
    statuses=Counter()
    inserted=0
    sum_original=Decimal("0.00")
    seen=set()
    preview=[]
    try:
        sheet=wb["PAYMENT EVIDENCE"] if "PAYMENT EVIDENCE" in wb else wb.active
        headers=tuple(sheet.cell(1,i).value for i in (1,2,3))
        insist(headers==SOURCE_HEADERS and sheet.cell(1,4).value in ("",None),
               "PAYMENT_SOURCE_HEADERS_CHANGED")
        for excel_row,cells in enumerate(sheet.iter_rows(min_row=2,max_col=4),start=2):
            if all(c.value in ("",None) for c in cells):
                continue
            observed+=1
            insist(observed<=30000,"PAYMENT_ROWS_EXCEED_LIMIT")
            desc,ff1=_norm_description(cells[0])
            rawsol,ff2=_norm_sol(cells[1])
            amount,ff3=_norm_credit(cells[2])
            reasons=list(ff1+ff2+ff3)
            if cells[3].value not in ("",None):
                reasons.append("EXTRA_COLUMN_NOT_ALLOWED")
            key=(desc,rawsol,amount)
            if key in seen:
                reasons.append("REPEATED_SOURCE_ROW_REVIEW")
            else:
                seen.add(key)
            # Match the already-validated original three-column source
            # arithmetic BEFORE applying stricter SOL/master-ledger rules.
            if not reasons:
                sum_original+=Decimal(amount)
            sol=canonical_sol(rawsol)
            if sol is None:
                reasons.append("SOL_ID_NOT_CANONICAL_TEXT")
            if reasons:
                status=STATUS_EXCLUDED
                branch=""
            else:
                # Prevent a possible repeat bank event across different
                # receipts being independently tallied without a UTR.
                duplicate=conn.execute(f"""
                    SELECT 1 FROM {TABLE}
                    WHERE owner_uid=? AND receipt_id<>?
                      AND description=? AND canonical_sol=? AND credit_amount=?
                    LIMIT 1
                """,(owner_uid,receipt_id,desc,sol,amount)).fetchone()
                branch=selected.get(sol,"")
                if duplicate:
                    reasons.append("CROSS_RECEIPT_DUPLICATE_CANDIDATE_REVIEW")
                    status=STATUS_DUPLICATE
                elif not branch:
                    reasons.append("SOL_MASTER_MAPPING_PENDING_OR_AMBIGUOUS")
                    status=STATUS_MASTER
                else:
                    status=STATUS_PENDING
            # Keep per-row exact raw SOL text and mapped branch, not guesses.
            conn.execute(f"""
                INSERT INTO {TABLE} (
                    owner_uid,receipt_id,excel_row,source_sha256,
                    description,sol_id_text,canonical_sol,
                    official_branch_name,credit_amount,review_reasons_json,
                    source_status,sol_master_sha256,created_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,(
                owner_uid,receipt_id,excel_row,source_sha256,desc,rawsol,
                sol or "",branch,amount,json.dumps(sorted(set(reasons))),
                status,master_digest,created_utc,
            ))
            inserted+=1
            statuses[status]+=1
            if len(preview)<50:
                preview.append({
                    "excel_row":excel_row,
                    "description":desc,
                    "sol_id":rawsol,
                    "branch_name":branch or "PENDING_SOL_MASTER",
                    "credit_amount":amount,
                    "review_flags":sorted(set(reasons)),
                    "ledger_status":status,
                })
    finally:
        wb.close()
    insist(inserted==original_parsed["source_rows"],
           "RECEIPT_PAYMENT_ROW_COUNT_MISMATCH")
    # Previously validated "valid" means structurally valid before official
    # master mapping, NOT reconciled.
    insist(sum_original==Decimal(original_parsed["valid_credit_total"]),
           "RECEIPT_VALID_CREDIT_TOTAL_MISMATCH")
    return {
        "payment_rows_recorded":inserted,
        "pending_reconciliation":statuses[STATUS_PENDING],
        "master_mapping_review":statuses[STATUS_MASTER],
        "duplicate_candidate_review":statuses[STATUS_DUPLICATE],
        "excluded_invalid_source":statuses[STATUS_EXCLUDED],
        "payment_received_records_only":True,
        "payment_preview":preview,
        "master_state":master_state,
        "original_file_unchanged":True,
        "financial_reconciliation_executed":False,
        "invoice_database_updated":False,
    }


def source_payment_rows(conn,owner_uid,*,after=0,limit=500,eligible_only=False):
    """Private future invoice-run input; only previously screened eligible rows.

    Exact user/receipt/source-row bindings enable a later v2.51 engine to run
    with NEW fresh invoices. R31 does not invoke a matching engine.
    """
    ensure_payment_schema(conn)
    insist(type(after) is int and after>=0 and type(limit) is int and
           1<=limit<=1000,"PAYMENT_LEDGER_PAGINATION_INVALID")
    filter_sql=" AND source_status=?" if eligible_only else ""
    args=[owner_uid,after]
    if eligible_only:
        args.append(STATUS_PENDING)
    args.append(limit)
    rows=conn.execute(f"""
        SELECT rowid,owner_uid,receipt_id,excel_row,source_sha256,
            description,sol_id_text,canonical_sol,official_branch_name,
            credit_amount,source_status,review_reasons_json
        FROM {TABLE}
        WHERE owner_uid=? AND rowid>? {filter_sql}
        ORDER BY rowid LIMIT ?
    """,args).fetchall()
    return tuple(dict(r) for r in rows)


def aggregate_sol_payment_report(conn,owner_uid):
    """Genuine R31 source sums. Matched=0 until VERIFIED engine writes exist."""
    ensure_payment_schema(conn)
    rows=conn.execute(f"""
        SELECT p.owner_uid,p.receipt_id,p.excel_row,p.description,p.sol_id_text,
          p.canonical_sol,p.official_branch_name,p.credit_amount,
          p.source_status,p.review_reasons_json,
          EXISTS (
            SELECT 1 FROM payment_reconciliation_verified_v1 v
            WHERE v.owner_uid=p.owner_uid AND v.receipt_id=p.receipt_id
              AND v.excel_row=p.excel_row
          ) AS has_verified_match
        FROM {TABLE} p
        WHERE p.owner_uid=?
        ORDER BY p.canonical_sol,p.receipt_id,p.excel_row
    """,(owner_uid,)).fetchall()
    groups={}
    detail=[]
    all_matched=all_uncalculated=all_excluded=0
    for r in rows:
        r=dict(r)
        groupid=r["canonical_sol"] or "(INVALID SOL)"
        group=groups.setdefault(groupid,{
            "sol_id":groupid,
            "branch_name":"",
            "payment_rows":0,"credit_total":Decimal("0.00"),
            "matched":0,"not_calculated":0,"excluded":0,
            "held_for_review":0,
        })
        # If mixed names appear under an SOL, do NOT select one arbitrarily.
        b=r["official_branch_name"]
        if b:
            if group["branch_name"] and group["branch_name"]!=b:
                group["branch_name"]="MASTER_IDENTITY_CONFLICT"
            elif not group["branch_name"]:
                group["branch_name"]=b
        group["payment_rows"]+=1
        amount=None
        try:
            amount=Decimal(r["credit_amount"])
            if amount.is_finite() and amount>0:group["credit_total"]+=amount
        except Exception:
            pass
        matched=bool(r["has_verified_match"])
        excluded=(r["source_status"]==STATUS_EXCLUDED)
        if excluded:
            group["excluded"]+=1;all_excluded+=1
            status="EXCLUDED"
        elif matched:
            group["matched"]+=1;all_matched+=1
            status="MATCHED_VERIFIED"
        else:
            group["not_calculated"]+=1;all_uncalculated+=1
            status="NOT_CALCULATED"
            if r["source_status"] in (STATUS_MASTER,STATUS_DUPLICATE):
                group["held_for_review"]+=1
        detail.append({
            "receipt_id":r["receipt_id"],"source_row":r["excel_row"],
            "sol_id":r["sol_id_text"],"branch_name":b or "PENDING_SOL_MASTER",
            "description":r["description"],"credit_amount":r["credit_amount"],
            "source_status":r["source_status"],"tally_status":status,
            "remarks":"; ".join(json.loads(r["review_reasons_json"])),
        })
    entries=[]
    for k,v in sorted(groups.items(),key=lambda item:item[0]):
        d=dict(v)
        d["credit_total"]=format(d["credit_total"],".2f")
        if not d["branch_name"]: d["branch_name"]="PENDING_SOL_MASTER"
        entries.append(d)
    return {
        "report":"SOL_WISE_PAYMENT_RECEIVED",
        "source":"PERSISTED_PAYMENT_EVIDENCE_ROWS",
        "master_v251_matrix_v239_connected":False,
        "reconciliation_executed":False,
        "formal_financial_certificate_required_for_report_deploy":False,
        "totals":{
            "payment_rows":len(rows),
            "matched":all_matched,
            "not_calculated":all_uncalculated,
            "excluded":all_excluded,
        },
        "sol_groups":entries,
        "details":detail,
        "financial_database_writes":0,
    }


def report_csv_bytes(report,*,detail=False):
    """CSV injection-safe: source description remains unchanged in SQLite."""
    cols=(
        ("Receipt ID","Source Excel Row","SOL ID","Branch Name",
         "Description","Credit Amount","Source Status","Tally Status","Remarks")
        if detail else
        ("SOL ID","Branch Name","Payment Rows","Credit Total",
         "Matched","Not Calculated","Excluded","Held for Review")
    )
    source=report["details"] if detail else report["sol_groups"]
    s=StringIO(newline="")
    writer=csv.writer(s)
    writer.writerow(cols)
    keys=(
        ("receipt_id","source_row","sol_id","branch_name","description",
         "credit_amount","source_status","tally_status","remarks")
        if detail else
        ("sol_id","branch_name","payment_rows","credit_total",
         "matched","not_calculated","excluded","held_for_review")
    )
    for row in source:
        vals=[]
        for field in keys:
            value=str(row.get(field,""))
            if value.startswith(("=","+","-","@")):
                value="'"+value
            vals.append(value)
        writer.writerow(vals)
    return s.getvalue().encode("utf-8-sig")
