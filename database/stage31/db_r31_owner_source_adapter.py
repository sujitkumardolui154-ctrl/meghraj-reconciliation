"""DB-R31 owner-scoped payment *source evidence* adapter — isolated QA only.

No allocation/reconciliation logic. No production connection. All owner IDs and
receipt IDs must come from authenticated server-side handlers and private SQLite
receipt storage, never an HTTP form field. Staging must have the *persistently*
reviewed owner-unique schema before this adapter can insert anything.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import uuid

QA_DB = "sbi_ft04g_clean_0e858f93"
QA_USER = "sbi_ft04q_ingest"
PARSER_VERSION = "R31_SOURCE_EVIDENCE_V1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
SOL = re.compile(r"[0-9]{1,12}\Z")


class SourceContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRow:
    number: int
    original: dict
    row_sha256: str
    amount_paise: int | None
    status: str
    reasons: tuple[str, ...]
    canonical_sol: str | None = None
    official_branch_name: str | None = None
    sol_master_sha256: str | None = None


@dataclass(frozen=True)
class SourcePlan:
    owner_uid: str
    receipt_id: str
    original_file_name: str
    source_sheet_name: str
    source_parser_version: str
    source_sha256: str
    rows: tuple[SourceRow, ...]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def row_json(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_sol(raw: str) -> str | None:
    if type(raw) is not str or SOL.fullmatch(raw) is None:
        return None
    return raw.lstrip("0") or None


def exact_paise(raw: str) -> int:
    if type(raw) is not str or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", raw):
        raise SourceContractError("INVALID_EXACT_CREDIT_TEXT")
    try:
        money = Decimal(raw)
    except InvalidOperation as exc:
        raise SourceContractError("INVALID_EXACT_CREDIT_TEXT") from exc
    value = money * 100
    if not value.is_finite() or value <= 0 or value != value.to_integral_value() or value > 10**15:
        raise SourceContractError("INVALID_CREDIT_PAISE")
    return int(value)


def authenticated_owner(user) -> str:
    """Pass only the actual Flask g.dil_user object, never request JSON."""
    uid = getattr(user, "uid", None)
    if type(uid) is not str or not uid or len(uid) > 200:
        raise SourceContractError("AUTHENTICATED_OWNER_REQUIRED")
    return uid


def build_plan(
    *, trusted_owner: str, trusted_receipt_id: str,
    original_file_name: str, source_sheet_name: str, raw_file: bytes,
    all_source_rows, parser_eligible_rows, parser_review_rows,
    approved_master_lookup=None,
) -> SourcePlan:
    """Build a lossless source plan from the existing app parser's exact decisions.

    all_source_rows: (source_row_number, {"Description","SOL ID","Credit Amount"}, local_error)
    parser_eligible_rows: (source_row_number, original_dict, exact_credit_paise)
    parser_review_rows: {"source_row":N, "reason":CODE}; both sets must partition all rows.

    Only a server-side, SHA-pinned approved master callback may return
    (official_branch_name, approved_master_sha256), else hold SOL for review.
    """
    if type(trusted_owner) is not str or not trusted_owner or len(trusted_owner) > 200:
        raise SourceContractError("AUTHENTICATED_OWNER_REQUIRED")
    if type(trusted_receipt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}",trusted_receipt_id):
        raise SourceContractError("PRIVATE_RECEIPT_ID_REQUIRED")
    if not isinstance(raw_file, bytes) or not 8 <= len(raw_file) <= 8*1024*1024:
        raise SourceContractError("IMMUTABLE_SOURCE_BYTES_REQUIRED")
    if (type(original_file_name) is not str or not original_file_name.endswith(".xlsx")
        or len(original_file_name) > 255 or "/" in original_file_name or "\\" in original_file_name):
        raise SourceContractError("ORIGINAL_FILE_NAME_INVALID")
    if type(source_sheet_name) is not str or not source_sheet_name.strip() or len(source_sheet_name)>80:
        raise SourceContractError("SOURCE_SHEET_IDENTITY_MISSING")
    actual={}
    for n,row,error in all_source_rows:
        if type(n) is not int or n < 2 or n in actual or type(row) is not dict:
            raise SourceContractError("ORIGINAL_SOURCE_ROW_AMBIGUOUS")
        if set(row) != {"Description","SOL ID","Credit Amount"} or any(type(x) is not str for x in row.values()):
            raise SourceContractError("ORIGINAL_SOURCE_CELLS_NOT_TEXT")
        actual[n]=(row,error)
    if not actual or len(actual)>20_000:
        raise SourceContractError("SOURCE_ROW_COUNT_INVALID")

    accepted={}
    for n,row,paise in parser_eligible_rows:
        if n not in actual or n in accepted or actual[n][0] != row:
            raise SourceContractError("PARSER_ELIGIBLE_ROW_MISMATCH")
        if type(paise) is not int or paise != exact_paise(row["Credit Amount"]):
            raise SourceContractError("PARSER_FINANCIAL_TOTAL_MISMATCH")
        if actual[n][1] or not row["Description"].strip() or canonical_sol(row["SOL ID"]) is None:
            raise SourceContractError("PARSER_APPROVED_INVALID_ROW")
        accepted[n]=paise
    reviewed={}
    for item in parser_review_rows:
        if not isinstance(item,dict) or set(item) != {"source_row","reason"}:
            raise SourceContractError("PARSER_REVIEW_FORMAT_INVALID")
        n=item["source_row"]
        if n not in actual or n in reviewed or n in accepted:
            raise SourceContractError("PARSER_REVIEW_ROW_MISMATCH")
        if type(item["reason"]) is not str or not item["reason"]:
            raise SourceContractError("PARSER_REVIEW_REASON_MISSING")
        reviewed[n]=item["reason"]
    if set(actual) != set(accepted)|set(reviewed):
        raise SourceContractError("PARSER_ROW_PARTITION_INCOMPLETE")
    counts=Counter(
        (actual[n][0]["Description"],actual[n][0]["SOL ID"],paise)
        for n,paise in accepted.items()
    )
    rows=[]
    for n in sorted(actual):
        original,error=actual[n]
        raw_sol=original["SOL ID"]
        canonical=canonical_sol(raw_sol)
        name=master_sha=None
        if n in accepted:
            if approved_master_lookup is not None and canonical is not None:
                approved=approved_master_lookup(canonical)
                if approved is not None:
                    if (type(approved) is not tuple or len(approved)!=2 or
                        type(approved[0]) is not str or not approved[0].strip() or
                        type(approved[1]) is not str or SHA.fullmatch(approved[1]) is None):
                        raise SourceContractError("APPROVED_MASTER_RESPONSE_UNVERIFIED")
                    name,master_sha=approved
            fingerprint=(original["Description"],raw_sol,accepted[n])
            if counts[fingerprint] > 1:
                status,reasons="HOLD_DUPLICATE_CANDIDATE",("REPEATED_SOURCE_CANDIDATE",)
            elif name is None:
                status,reasons="HOLD_SOL_MASTER",("APPROVED_SOL_MASTER_MISSING_OR_UNVERIFIED",)
            else:
                status,reasons="PENDING_RECONCILIATION",()
        else:
            status,reasons="EXCLUDED_INVALID_SOURCE",(reviewed[n],)
        rows.append(SourceRow(
            n,original,sha256(row_json(original).encode("utf-8")),
            accepted.get(n),status,reasons,canonical,name,master_sha))
    return SourcePlan(
        trusted_owner,trusted_receipt_id,original_file_name,source_sheet_name,
        PARSER_VERSION,sha256(raw_file),tuple(rows))


def assert_owner_scoped_qa(cur) -> None:
    """Read-only preflight: reject global SHA or unauthorised writer."""
    cur.execute("""SELECT current_database(),current_user,
      has_table_privilege(current_user,'sbi.import_batches','INSERT'),
      has_table_privilege(current_user,'sbi.payment_source_rows','INSERT'),
      has_table_privilege(current_user,'sbi.payments','INSERT'),
      has_table_privilege(current_user,'sbi.payment_source_status_v1','INSERT'),
      has_table_privilege(current_user,'sbi.payments','UPDATE'),
      has_table_privilege(current_user,'sbi.payments','DELETE')""")
    if tuple(cur.fetchone()) != (QA_DB,QA_USER,True,True,True,True,False,False):
        raise RuntimeError("R31_QA_DB_ROLE_MISMATCH")
    cur.execute("""SELECT
      (SELECT count(*) FROM pg_indexes WHERE schemaname='sbi'
         AND indexname='ux_r31_qa_owned_source_sha'),
      (SELECT count(*) FROM pg_indexes WHERE schemaname='sbi'
         AND indexname='ux_r31_qa_legacy_source_sha'),
      (SELECT count(*) FROM pg_constraint WHERE
         conrelid='sbi.import_batches'::regclass AND contype='u'
         AND pg_get_constraintdef(oid) LIKE
         'UNIQUE (source_system, source_kind, source_sha256)%')""")
    if tuple(cur.fetchone()) != (1,1,0):
        raise RuntimeError("R31_OWNER_SCOPE_QA_SCHEMA_NOT_APPROVED")


def _verify_existing(cur, batch_id, plan):
    cur.execute("""SELECT r.source_row_number,r.row_sha256,
       p.credit_paise,p.description,p.sol_id
       FROM sbi.payment_source_rows r
       LEFT JOIN sbi.payments p ON p.source_row_id=r.id
       WHERE r.batch_id=%s ORDER BY r.source_row_number""",(batch_id,))
    got=[(int(n),str(h),None if paise is None else int(paise),desc,sol)
         for n,h,paise,desc,sol in cur.fetchall()]
    expected=[(r.number,r.row_sha256,r.amount_paise,
               r.original["Description"] if r.amount_paise is not None else None,
               r.original["SOL ID"] if r.amount_paise is not None else None)
              for r in plan.rows]
    if got != expected:
        raise RuntimeError("R31_IMMUTABLE_SOURCE_REPLAY_CONFLICT")
    cur.execute("""SELECT count(*) FROM sbi.payment_source_rows r
       JOIN sbi.payment_source_status_v1 st ON st.source_row_id=r.id
       WHERE r.batch_id=%s""",(batch_id,))
    if int(cur.fetchone()[0]) != len(plan.rows):
        raise RuntimeError("R31_STATUS_EVIDENCE_REPLAY_INCOMPLETE")


def persist_qa_source(conn, plan: SourcePlan) -> str:
    """Atomically record all source rows; create payments only for valid amounts.

    The caller owns private receipt verification and database connection.
    Requires an isolated QA role+persistently owner-scoped schema; not runnable
    on the current reverted global-SHA schema or production DB.
    """
    if not isinstance(plan,SourcePlan):
        raise SourceContractError("SOURCE_PLAN_REQUIRED")
    with conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            cur.execute("SET LOCAL lock_timeout='2s'")
            assert_owner_scoped_qa(cur)
            cur.execute("""SELECT id FROM sbi.import_batches
               WHERE owner_uid=%s AND source_system='excel'
               AND source_kind='payment' AND source_sha256=%s""",
               (plan.owner_uid,plan.source_sha256))
            previous=cur.fetchall()
            if len(previous)>1:
                raise RuntimeError("R31_MULTIPLE_OWNER_BATCHES")
            if previous:
                _verify_existing(cur,previous[0][0],plan)
                return "ALREADY_RECORDED"
            batch_id=str(uuid.uuid4())
            cur.execute("""INSERT INTO sbi.import_batches
              (id,source_system,source_kind,original_file_name,source_sha256,
               owner_uid,source_receipt_id,source_sheet_name,source_parser_version)
               VALUES (%s,'excel','payment',%s,%s,%s,%s,%s,%s)""",
               (batch_id,plan.original_file_name,plan.source_sha256,
                plan.owner_uid,plan.receipt_id,plan.source_sheet_name,
                plan.source_parser_version))
            for row in plan.rows:
                source_id=str(uuid.uuid4())
                cur.execute("""INSERT INTO sbi.payment_source_rows
                  (id,batch_id,source_row_number,original_values,row_sha256)
                  VALUES (%s,%s,%s,%s::jsonb,%s)""",
                  (source_id,batch_id,row.number,row_json(row.original),row.row_sha256))
                if row.amount_paise is not None:
                    cur.execute("""INSERT INTO sbi.payments
                      (id,source_row_id,description,sol_id,credit_paise)
                      VALUES (%s,%s,%s,%s,%s)""",
                      (str(uuid.uuid4()),source_id,row.original["Description"],
                       row.original["SOL ID"],row.amount_paise))
                cur.execute("""INSERT INTO sbi.payment_source_status_v1
                  (source_row_id,source_status,reason_codes,parser_version,
                   canonical_sol,official_branch_name,sol_master_sha256)
                  VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s)""",
                  (source_id,row.status,json.dumps(list(row.reasons)),
                   plan.source_parser_version,row.canonical_sol,
                   row.official_branch_name,row.sol_master_sha256))
    return "SOURCE_COMMITTED_NOT_RECONCILED"
