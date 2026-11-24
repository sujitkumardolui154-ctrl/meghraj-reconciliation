"""R31 source-only PostgreSQL report contract (not a settlement report).

All SQL is parameterized and requires trusted g.dil_user.uid on the server.
Do not expose these statements as anonymous routes or grant direct view access.
"""
from __future__ import annotations
import csv
import io

# Owner uid is always a parameter supplied by authenticated middleware.
# No allocation table join: a payment's credit is never multiplied.
SOL_SUMMARY_SQL = """
SELECT
  COALESCE(raw_sol,'') AS raw_sol,
  COALESCE(official_branch_name,'') AS official_branch_name,
  sol_master_sha256,
  count(*)::bigint AS uploaded_source_rows,
  count(payment_id)::bigint AS valid_received_rows,
  COALESCE(sum(credit_paise),0)::bigint AS received_credit_paise,
  count(*) FILTER (WHERE source_status='PENDING_RECONCILIATION')::bigint
     AS pending_reconciliation_rows,
  count(*) FILTER (WHERE source_status='EXCLUDED_INVALID_SOURCE')::bigint
     AS excluded_invalid_rows,
  count(*) FILTER (WHERE source_status IN
     ('HOLD_SOL_MASTER','HOLD_DUPLICATE_CANDIDATE','REVIEW_REQUIRED'))::bigint
     AS held_rows,
  count(*) FILTER (WHERE source_status='UNCLASSIFIED_LEGACY')::bigint
     AS legacy_unclassified_rows,
  NULL::bigint AS verified_matched_payment_rows,
  NULL::bigint AS verified_allocated_paise,
  NULL::bigint AS remaining_after_run_paise,
  'NOT_CALCULATED'::text AS reconciliation_status
FROM sbi.payment_received_source_v1
WHERE owner_uid = %s
GROUP BY raw_sol, official_branch_name, sol_master_sha256
ORDER BY raw_sol, official_branch_name
LIMIT %s OFFSET %s
"""

PAYMENT_DETAILS_SQL = """
SELECT
  source_receipt_id, source_sha256, source_sheet_name,
  source_row_number, description, raw_sol,
  raw_credit_amount, credit_paise, official_branch_name,
  sol_master_sha256, source_status,
  reason_codes::text AS reason_codes,
  'NOT_CALCULATED'::text AS reconciliation_status,
  NULL::text AS verified_invoice_refs
FROM sbi.payment_received_source_v1
WHERE owner_uid = %s
ORDER BY source_sha256, source_row_number
LIMIT %s OFFSET %s
"""

SOL_CSV_FIELDS = (
    'raw_sol','official_branch_name','sol_master_sha256',
    'uploaded_source_rows','valid_received_rows','received_credit_paise',
    'pending_reconciliation_rows','excluded_invalid_rows','held_rows',
    'legacy_unclassified_rows','verified_matched_payment_rows',
    'verified_allocated_paise','remaining_after_run_paise',
    'reconciliation_status'
)
DETAIL_CSV_FIELDS = (
    'source_receipt_id','source_sha256','source_sheet_name',
    'source_row_number','description','raw_sol','raw_credit_amount',
    'credit_paise','official_branch_name','sol_master_sha256',
    'source_status','reason_codes','reconciliation_status',
    'verified_invoice_refs'
)


def validate_page(limit: int, offset: int) -> tuple[int,int]:
    if type(limit) is not int or type(offset) is not int:
        raise ValueError('PAGINATION_REQUIRES_INTEGERS')
    if limit < 1 or limit > 1000 or offset < 0 or offset > 10000000:
        raise ValueError('PAGINATION_OUT_OF_RANGE')
    return limit,offset


def query_args(owner_uid: str, limit: int = 100, offset: int = 0):
    if type(owner_uid) is not str or not owner_uid or len(owner_uid) > 200:
        raise ValueError('SERVER_AUTHENTICATED_OWNER_REQUIRED')
    limit,offset = validate_page(limit,offset)
    return (owner_uid,limit,offset)


def csv_safe(value) -> str:
    """Escape spreadsheet formula prefixes without altering DB evidence."""
    if value is None:
        return ''
    text = str(value)
    lead = text.lstrip(' \t\r\n')
    if lead.startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')):
        return "'" + text
    return text


def csv_export(rows, fields) -> bytes:
    if tuple(fields) not in (SOL_CSV_FIELDS,DETAIL_CSV_FIELDS):
        raise ValueError('UNAPPROVED_CSV_FIELDS')
    output = io.StringIO(newline='')
    writer = csv.writer(output,lineterminator='\r\n')
    writer.writerow(fields)
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError('REPORT_ROW_MUST_BE_NAMED')
        writer.writerow([csv_safe(row.get(field)) for field in fields])
    return output.getvalue().encode('utf-8-sig')
