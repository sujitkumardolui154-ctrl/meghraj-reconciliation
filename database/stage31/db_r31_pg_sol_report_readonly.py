"""DB-R31.4: owner-scoped PostgreSQL payment-source report adapter.

Reads existing sbi.payment_received_source_v1 under an actual read-only DB
role and read-only transaction. Does not depend on R31's SQLite business
ledger. No allocation joins, SQL writes, bank status changes, or fake MATCHED.
This is a private staging integration candidate, NOT a registered production
Flask route. Caller must verify Firebase g.dil_user UID and report permission.
"""
from __future__ import annotations
import csv
from decimal import Decimal
import io
from db_r31_source_report_contract import csv_safe, query_args

DB_PRODUCTION = "sbi_reconciliation_main"
DB_QA = "sbi_ft04g_clean_0e858f93"
ROLE_PRODUCTION = "sbi_pr129_report_login"
ROLE_QA = "sbi_ft04q_report"
ALLOWED_IDENTITY = frozenset((
    (DB_PRODUCTION, ROLE_PRODUCTION),
    (DB_QA, ROLE_QA),
))

# One group per normalized SOL even when raw evidence says 001505 / 1505.
# Never claim a group has one verified official branch if ANY source row's
# master is missing, or more than one master/version/official label exists.
# Source status is not a bank settlement.
SOL_WISE_SUMMARY_SQL = """
WITH source AS (
 SELECT source_row_id,
        COALESCE(NULLIF(canonical_sol,''),
          CASE WHEN raw_sol ~ '^[0-9]+$'
               THEN NULLIF(ltrim(raw_sol,'0'),'')
               ELSE NULL END,
          raw_sol, '(MISSING SOL)') AS sol_id,
        official_branch_name,sol_master_sha256,
        payment_id,credit_paise,source_status
 FROM sbi.payment_received_source_v1
 WHERE owner_uid = %s
)
SELECT
 sol_id,
 CASE
   WHEN count(payment_id)>0
     AND count(*) FILTER (
          WHERE payment_id IS NOT NULL AND (
                official_branch_name IS NULL
             OR length(trim(official_branch_name))=0
             OR sol_master_sha256 IS NULL)) = 0
     AND count(DISTINCT official_branch_name)
          FILTER (WHERE payment_id IS NOT NULL)=1
     AND count(DISTINCT sol_master_sha256)
          FILTER (WHERE payment_id IS NOT NULL)=1
   THEN max(official_branch_name)
          FILTER (WHERE payment_id IS NOT NULL)
   ELSE 'PENDING_SOL_MASTER_REVIEW'
 END AS branch_name,
 count(*)::bigint AS payment_rows,
 count(payment_id)::bigint AS valid_payment_rows,
 COALESCE(sum(credit_paise),0)::bigint AS credit_paise,
 count(*) FILTER (
   WHERE source_status='EXCLUDED_INVALID_SOURCE'
 )::bigint AS excluded,
 count(*) FILTER (
   WHERE source_status IN
     ('HOLD_SOL_MASTER','HOLD_DUPLICATE_CANDIDATE','REVIEW_REQUIRED')
 )::bigint AS held_for_review,
 count(*) FILTER (
   WHERE source_status <> 'EXCLUDED_INVALID_SOURCE'
 )::bigint AS not_calculated,
 count(*) FILTER (
   WHERE source_status='PENDING_RECONCILIATION'
 )::bigint AS available_for_future_matching,
 count(*) FILTER (
   WHERE source_status='UNCLASSIFIED_LEGACY'
 )::bigint AS legacy_unclassified,
 NULL::bigint AS matched,
 NULL::bigint AS verified_allocated_paise
FROM source
GROUP BY sol_id
ORDER BY sol_id
LIMIT %s OFFSET %s
"""

PAYMENT_ROW_DETAILS_SQL = """
SELECT source_receipt_id,source_sha256,source_row_id,source_row_number,
       description,raw_sol,canonical_sol,raw_credit_amount,credit_paise,
       official_branch_name,sol_master_sha256,source_status,
       reason_codes::text AS reason_codes,
       'NOT_CALCULATED'::text AS reconciliation_status,
       NULL::text AS verified_invoice_refs
FROM sbi.payment_received_source_v1
WHERE owner_uid = %s
ORDER BY source_sha256,source_row_number
LIMIT %s OFFSET %s
"""

SUMMARY_FIELDS = (
    "sol_id","branch_name","payment_rows","valid_payment_rows",
    "credit_paise","excluded","held_for_review","not_calculated",
    "available_for_future_matching","legacy_unclassified",
    "matched","verified_allocated_paise",
)
DETAIL_FIELDS = (
    "source_receipt_id","source_sha256","source_row_id","source_row_number",
    "description","raw_sol","canonical_sol","raw_credit_amount",
    "credit_paise","official_branch_name","sol_master_sha256",
    "source_status","reason_codes","reconciliation_status",
    "verified_invoice_refs",
)


class ReportAccessRefused(ValueError):
    pass


def _with_rows(connection, sql, params):
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout='5s'")
            cursor.execute("SELECT current_database(), current_user")
            identity=tuple(cursor.fetchone())
            if identity not in ALLOWED_IDENTITY:
                raise ReportAccessRefused("REPORT_ONLY_DATABASE_ROLE_REQUIRED")
            cursor.execute(sql, params)
            description=cursor.description
            if not description:
                raise ReportAccessRefused("REPORT_COLUMN_DESCRIPTION_REQUIRED")
            fields=tuple(d.name for d in description)
            expected=SUMMARY_FIELDS if sql==SOL_WISE_SUMMARY_SQL else DETAIL_FIELDS
            if fields!=expected:
                raise ReportAccessRefused("REPORT_UNEXPECTED_QUERY_SCHEMA")
            rows=cursor.fetchall()
    return [dict(zip(fields,row)) for row in rows]


def sol_summary(connection, *, trusted_owner_uid, limit=100, offset=0):
    """Owner identity is supplied by VERIFIED server middleware, not request."""
    params=query_args(trusted_owner_uid,limit,offset)
    records=_with_rows(connection,SOL_WISE_SUMMARY_SQL,params)
    totals={
        "payment_rows":sum(x["payment_rows"] for x in records),
        "not_calculated":sum(x["not_calculated"] for x in records),
        "excluded":sum(x["excluded"] for x in records),
        "held_for_review":sum(x["held_for_review"] for x in records),
        "credit_paise":sum(x["credit_paise"] for x in records),
        "matched":None,
    }
    # Totals are PAGE totals; never claim they represent all owners or pages.
    return {
        "report":"SBI_SOL_WISE_PAYMENT_EVIDENCE",
        "source":"CENTRAL_POSTGRESQL_PAYMENT_SOURCE_VIEW",
        "owner_filter":"SERVER_UID_PARAMETER",
        "records":records,"page_totals":totals,
        "limit":limit,"offset":offset,
        "full_reconciliation_engine_connected":False,
        "reconciliation_executed":False,
        "verified_matched_status_available":False,
        "financial_writes":False,
    }


def payment_details(connection, *, trusted_owner_uid, limit=100, offset=0):
    params=query_args(trusted_owner_uid,limit,offset)
    records=_with_rows(connection,PAYMENT_ROW_DETAILS_SQL,params)
    return {
        "report":"SBI_INDIVIDUAL_PAYMENT_SOURCE_ROWS",
        "source":"CENTRAL_POSTGRESQL_PAYMENT_SOURCE_VIEW",
        "records":records,"limit":limit,"offset":offset,
        "reconciliation_executed":False,
        "financial_writes":False,
    }


def safe_csv(records, *, detail=False):
    fields=DETAIL_FIELDS if detail else SUMMARY_FIELDS
    output=io.StringIO(newline="")
    writer=csv.writer(output,lineterminator="\r\n")
    writer.writerow(fields)
    for record in records:
        if type(record) is not dict:
            raise ReportAccessRefused("REPORT_ROW_NOT_NAMED")
        writer.writerow([csv_safe(record.get(f)) for f in fields])
    return output.getvalue().encode("utf-8-sig")
