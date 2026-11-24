"""DB-R31.3: source-preserving FT-04 --> existing PostgreSQL QA ingest adapter.

This module is expressly restricted to physically isolated synthetic
sbi_ft04g_clean_0e858f93 with INSERT-only QA writer. It does not connect
to the central financial database, import a web request, authenticate a user,
run reconciliation or decide whether bank credit was actually received.

Input rows are supplied by the verified FT-04 parser + original application
parser. Caller MUST bind owner UID from the validated server Firebase session,
not a browser field. All source rows (including rejected rows) are retained in
sbi.payment_source_rows with status; only structurally valid positive credit
rows enter sbi.payments, and only eligible rows may be proposed for matching.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import uuid

QA_DB = "sbi_ft04g_clean_0e858f93"
QA_ROLE = "sbi_ft04q_ingest"
PARSER_VERSION = "DB_R31_FT04_ROW_CONTRACT_V1"
SOURCE_FIELDS = ("Description", "SOL ID", "Credit Amount")
STATUS_PASS = "PENDING_RECONCILIATION"
STATUS_MASTER = "HOLD_SOL_MASTER"
STATUS_DUP = "HOLD_DUPLICATE_CANDIDATE"
STATUS_BAD = "EXCLUDED_INVALID_SOURCE"
VALID_STATUSES = frozenset((STATUS_PASS, STATUS_MASTER, STATUS_DUP, STATUS_BAD))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT = re.compile(r"[0-9a-f]{32}\Z")
_SOL = re.compile(r"[0-9]{1,12}\Z")
_REASON = re.compile(r"[A-Z0-9_:-]{3,100}\Z")
_MAX_ROWS = 20000
_MAX_FILE_BYTES = 8 * 1024 * 1024


class IngestReviewRequired(ValueError):
    """Code-only rejection; do not expose individual customer data."""


def require(condition, code):
    if not condition:
        raise IngestReviewRequired(code)


def canonical_sol(raw):
    if type(raw) is not str or _SOL.fullmatch(raw) is None:
        return None
    return raw.lstrip("0") or None


def canonical_json(row):
    return json.dumps(row, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


@dataclass(frozen=True)
class ReceiptRow:
    excel_row: int
    original_json: str
    row_sha256: str
    description: str
    raw_sol: str
    credit_paise: int | None
    status: str
    reasons: tuple[str, ...]
    canonical_sol: str | None
    official_branch_name: str | None


@dataclass(frozen=True)
class ReceiptPlan:
    owner_uid: str
    receipt_id: str
    file_sha256: str
    original_filename: str
    source_sheet_name: str
    master_sha256: str | None
    rows: tuple[ReceiptRow, ...]
    accepted_credit_paise: int
    parser_version: str = PARSER_VERSION


def _exact_paise(value):
    try:
        number = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError):
        raise IngestReviewRequired("SOURCE_CREDIT_TOTAL_INVALID") from None
    require(number.is_finite() and number >= 0 and
            number == number.to_integral_value(),
            "SOURCE_CREDIT_TOTAL_NOT_EXACT_PAISE")
    return int(number)


def build_receipt_plan(payload, original_parser, extract_all,
                       classify_rows, *, owner_uid, receipt_id,
                       source_sheet_name, approved_sol_by_key,
                       master_sha256=None, filename="payment-evidence.xlsx"):
    """Combine exact original parser totals and all FT-04 row decisions.

    No DB access. Do not use this module to parse financial bank events by
    itself; FT-04 supplies both row extraction and parser-equivalent decisions.
    """
    require(type(payload) is bytes and 0 < len(payload) <= _MAX_FILE_BYTES,
            "SOURCE_FILE_SIZE_OR_TYPE")
    require(type(owner_uid) is str and bool(owner_uid.strip()) and
            len(owner_uid) <= 200 and not any(ord(x) < 32 for x in owner_uid),
            "TRUSTED_OWNER_UID_REQUIRED")
    require(type(receipt_id) is str and _RECEIPT.fullmatch(receipt_id),
            "IMMUTABLE_RECEIPT_ID_REQUIRED")
    require(type(source_sheet_name) is str and bool(source_sheet_name.strip())
            and len(source_sheet_name) <= 100,
            "VERIFIED_SOURCE_SHEET_REQUIRED")
    require(type(filename) is str and bool(filename)
            and len(filename) <= 160 and "/" not in filename
            and "\\" not in filename and filename.endswith(".xlsx"),
            "SOURCE_FILENAME_INVALID")
    require(type(approved_sol_by_key) is dict and
            all(type(key) is str and canonical_sol(key) == key and
                type(name) is str and bool(name.strip()) and len(name) <= 180
                for key, name in approved_sol_by_key.items()),
            "APPROVED_SOL_LOOKUP_INVALID")
    require((bool(approved_sol_by_key) and type(master_sha256) is str
             and _SHA.fullmatch(master_sha256)) or
            (not approved_sol_by_key and master_sha256 is None),
            "APPROVED_SOL_MASTER_SHA_REQUIRED")
    for callable_ in (original_parser, extract_all, classify_rows):
        require(callable(callable_), "VERIFIED_FT04_PARSERS_REQUIRED")

    parsed = original_parser(payload)
    raw_rows = extract_all(payload)
    accepted, rejected = classify_rows(payload, original_parser)
    require(type(parsed) is dict and type(raw_rows) is list
            and type(accepted) is list and type(rejected) is list
            and 0 < len(raw_rows) <= _MAX_ROWS,
            "SOURCE_ROWS_UNVERIFIED")
    require(len(raw_rows) == parsed.get("source_rows")
            and len(accepted) == parsed.get("valid_rows")
            and len(rejected) == parsed.get("review_rows"),
            "SOURCE_PARSER_ROW_PARITY_FAILED")

    good = {}
    for item in accepted:
        require(type(item) is tuple and len(item) == 3,
                "FT04_ACCEPTED_ROW_CONTRACT")
        row_number, row, amount = item
        require(type(row_number) is int and row_number >= 2 and
                type(row) is dict and type(amount) is int and amount > 0,
                "FT04_ACCEPTED_ROW_INVALID")
        require(row_number not in good, "DUPLICATE_FT04_ACCEPTED_ROW")
        good[row_number] = (row, amount)
    bad = {}
    for item in rejected:
        require(type(item) is dict and
                type(item.get("source_row")) is int and
                type(item.get("reason")) is str,
                "FT04_REJECTED_ROW_CONTRACT")
        idx = item["source_row"]
        reason = item["reason"]
        require(_REASON.fullmatch(reason) and idx not in bad,
                "FT04_INVALID_REVIEW_REASON")
        bad[idx] = reason
    require(not(set(good) & set(bad)), "FT04_ROW_CLASSIFICATION_CONFLICT")
    observed_rows = {t[0] for t in raw_rows}
    require(observed_rows == set(good) | set(bad)
            and len(observed_rows) == len(raw_rows),
            "FT04_SOURCE_ROW_COVERAGE_FAILED")
    accepted_paise = sum(paise for _,paise in good.values())
    require(accepted_paise == _exact_paise(parsed.get("valid_credit_total")),
            "FT04_ACCEPTED_CREDIT_PARITY_FAILED")

    # Similar-looking entries inside a file may be separate bank events.
    # Hold *both* as duplicate candidates rather than automatically settle.
    fingerprints = Counter()
    for row_number, (entry, paise) in good.items():
        require(all(type(entry.get(field)) is str for field in SOURCE_FIELDS),
                "FT04_ACCEPTED_FIELD_TYPE_INVALID")
    # The existing approved parser may exclude the *second* repeated row,
    # leaving the first apparently accepted. Inspect ALL original source
    # records so the first candidate is also held from automatic matching.
    for _, original, _ in raw_rows:
        if type(original) is dict and set(original) == set(SOURCE_FIELDS):
            try:
                exact = Decimal(str(original["Credit Amount"])) * 100
                if exact.is_finite() and exact > 0 and exact == exact.to_integral_value():
                    fingerprints[(original["Description"],original["SOL ID"],
                                  int(exact))] += 1
            except (InvalidOperation,ValueError,TypeError):
                pass

    planned = []
    for number, entry, row_error in raw_rows:
        require(type(number) is int and number >= 2 and type(entry) is dict
                and set(entry) == set(SOURCE_FIELDS),
                "SOURCE_ROW_SHAPE_INVALID")
        require(all(type(entry[field]) is str for field in SOURCE_FIELDS),
                "RAW_SOURCE_ROW_NON_STRING_UNVERIFIED")
        raw_json = canonical_json(entry)
        raw_sol = entry["SOL ID"]
        description = entry["Description"]
        sol = canonical_sol(raw_sol)
        reasons = []
        credit = None
        if number in bad:
            reasons.append(bad[number])
            status = STATUS_BAD
            branch = None
        else:
            original, credit = good[number]
            require(original == entry, "FT04_SOURCE_VALUES_DIFFER_FROM_ACCEPTED")
            require(sol is not None, "ACCEPTED_SOL_INVALID")
            branch = approved_sol_by_key.get(sol)
            if not branch:
                reasons.append("SOL_MASTER_MAPPING_PENDING")
                status = STATUS_MASTER
            elif fingerprints[(description, raw_sol, credit)] > 1:
                reasons.append("INTRA_FILE_DUPLICATE_CANDIDATE")
                status = STATUS_DUP
            else:
                status = STATUS_PASS
        require(status in VALID_STATUSES and
                all(_REASON.fullmatch(x) for x in reasons),
                "ROW_REVIEW_REASON_UNSAFE")
        planned.append(ReceiptRow(
            number, raw_json, sha256(raw_json.encode("utf-8")).hexdigest(),
            description, raw_sol, credit, status,
            tuple(reasons), sol, branch))
    return ReceiptPlan(owner_uid, receipt_id, sha256(payload).hexdigest(),
                       filename, source_sheet_name, master_sha256,
                       tuple(planned), accepted_paise)


def _existing_matches(cur, batch_id, plan):
    """Replayed receipt is idempotent only if *every* stored row agrees."""
    cur.execute("""
      SELECT r.source_row_number, r.row_sha256, p.credit_paise,
             st.source_status
        FROM sbi.payment_source_rows r
        LEFT JOIN sbi.payments p ON p.source_row_id=r.id
        LEFT JOIN sbi.payment_source_status_v1 st ON st.source_row_id=r.id
       WHERE r.batch_id=%s
       ORDER BY r.source_row_number
    """, (batch_id,))
    actual = cur.fetchall()
    expected = [(x.excel_row, x.row_sha256, x.credit_paise, x.status)
                for x in plan.rows]
    require([tuple(x) for x in actual] == expected,
            "PREVIOUS_SOURCE_RECEIPT_DIFFERS")
    return True


def write_qa_source_receipt(conn, plan):
    """Insert-only, transaction-scoped; physical QA database only.

    Existing FT-04 QA role may require a separately approved *QA-only* INSERT
    grant on the new source status table. Never acquire credentials here.
    """
    require(type(plan) is ReceiptPlan and plan.rows,
            "SOURCE_PLAN_REQUIRED")
    # psycopg context manager supplies transaction rollback on exception.
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user")
            require(tuple(cur.fetchone()) == (QA_DB, QA_ROLE),
                    "QA_ONLY_DATABASE_AND_ROLE_REQUIRED")
            cur.execute("""
              SELECT has_table_privilege(current_user,'sbi.import_batches','INSERT'),
                     has_table_privilege(current_user,'sbi.payment_source_rows','INSERT'),
                     has_table_privilege(current_user,'sbi.payments','INSERT'),
                     has_table_privilege(current_user,'sbi.payment_source_status_v1','INSERT'),
                     has_table_privilege(current_user,'sbi.payments','UPDATE'),
                     has_table_privilege(current_user,'sbi.payments','DELETE')
            """)
            require(tuple(cur.fetchone()) == (True, True, True, True, False, False),
                    "QA_INSERT_ONLY_STATUS_ROLE_NOT_READY")
            cur.execute("SET LOCAL statement_timeout='10s'")
            cur.execute("SET LOCAL lock_timeout='2s'")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                        (plan.owner_uid,))
            cur.execute("""
              SELECT id, owner_uid, source_receipt_id
                FROM sbi.import_batches
               WHERE source_system='excel' AND source_kind='payment'
                 AND source_sha256=%s
               FOR UPDATE
            """, (plan.file_sha256,))
            existing = cur.fetchall()
            require(len(existing) <= 1, "GLOBAL_SOURCE_SHA_MULTIPLE_BATCHES")
            if existing:
                batch_id, owner_uid, old_receipt = existing[0]
                require(owner_uid == plan.owner_uid,
                        "GLOBAL_SHA_CROSS_OWNER_REVIEW_REQUIRED")
                require(old_receipt == plan.receipt_id,
                        "SAME_FILE_DIFFERENT_RECEIPT_REVIEW_REQUIRED")
                _existing_matches(cur, batch_id, plan)
                return {"status": "QA_ALREADY_RECORDED",
                        "source_rows": len(plan.rows),
                        "candidate_rows": sum(x.status == STATUS_PASS for x in plan.rows),
                        "financial_allocations": 0, "production_writes": False}

            batch_id = str(uuid.uuid4())
            cur.execute("""
              INSERT INTO sbi.import_batches
                (id,source_system,source_kind,original_file_name,source_sha256,
                 owner_uid,source_receipt_id,source_sheet_name,source_parser_version)
              VALUES (%s,'excel','payment',%s,%s,%s,%s,%s,%s)
            """, (batch_id, plan.original_filename, plan.file_sha256,
                  plan.owner_uid, plan.receipt_id, plan.source_sheet_name,
                  plan.parser_version))
            for record in plan.rows:
                source_id = str(uuid.uuid4())
                cur.execute("""
                  INSERT INTO sbi.payment_source_rows
                    (id,batch_id,source_row_number,original_values,row_sha256)
                  VALUES (%s,%s,%s,%s::jsonb,%s)
                """, (source_id, batch_id, record.excel_row,
                      record.original_json, record.row_sha256))

                status = record.status
                reasons = list(record.reasons)
                # Same-looking receipt credit may be a legitimate new bank
                # event. Hold only this row; never silently omit or settle.
                if record.credit_paise is not None and status == STATUS_PASS:
                    cur.execute("""
                      SELECT 1 FROM sbi.payments p
                      JOIN sbi.payment_source_rows r ON r.id=p.source_row_id
                      JOIN sbi.import_batches b ON b.id=r.batch_id
                      WHERE b.owner_uid=%s AND b.id<>%s
                        AND p.description=%s AND p.sol_id=%s
                        AND p.credit_paise=%s
                      LIMIT 1
                    """, (plan.owner_uid, batch_id, record.description,
                          record.raw_sol, record.credit_paise))
                    if cur.fetchone() is not None:
                        status = STATUS_DUP
                        reasons = ["CROSS_RECEIPT_DUPLICATE_CANDIDATE"]
                if record.credit_paise is not None:
                    cur.execute("""
                      INSERT INTO sbi.payments
                        (id,source_row_id,description,sol_id,credit_paise)
                      VALUES (%s,%s,%s,%s,%s)
                    """, (str(uuid.uuid4()), source_id,
                          record.description, record.raw_sol,
                          record.credit_paise))
                cur.execute("""
                  INSERT INTO sbi.payment_source_status_v1
                    (source_row_id,source_status,reason_codes,parser_version,
                     canonical_sol,official_branch_name,sol_master_sha256)
                  VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s)
                """, (source_id, status, json.dumps(reasons),
                      plan.parser_version, record.canonical_sol,
                      record.official_branch_name if plan.master_sha256 else None,
                      plan.master_sha256))
    return {"status": "QA_SOURCE_ROWS_COMMITTED",
            "source_rows": len(plan.rows),
            "valid_credit_paise": plan.accepted_credit_paise,
            "financial_allocations": 0, "production_writes": False}
