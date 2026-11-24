"""DB-R31 source-only SOL reports under authenticated QA owner context.

No Flask route is registered here. This is a private server-side adapter; use
real Firebase middleware to populate trusted g.dil_user before calling.
No finance results/allocations; received source credit is not matched credit.
"""
from __future__ import annotations

from db_r31_owner_source_adapter import QA_DB, authenticated_owner
from db_r31_source_report_contract import (
    SOL_SUMMARY_SQL, PAYMENT_DETAILS_SQL,
    SOL_CSV_FIELDS, DETAIL_CSV_FIELDS,
    query_args, csv_export,
)

QA_REPORT_ROLE = "sbi_r31_ownerqa_report"


def _assert_report_role(cur) -> None:
    cur.execute("""SELECT current_database(), current_user,
      has_table_privilege(current_user,'sbi.payments','INSERT'),
      has_table_privilege(current_user,'sbi.payments','UPDATE'),
      has_table_privilege(current_user,'sbi.payments','DELETE')""")
    if tuple(cur.fetchone()) != (QA_DB,QA_REPORT_ROLE,False,False,False):
        raise RuntimeError("R31_QA_REPORT_ROLE_MISMATCH")
    # The versioned view must exist and be deliberately owner-filtered by this
    # authenticated server-side module. Do not grant public/browser DB access.


def _execute_readonly(conn, user, query, limit, offset):
    owner=authenticated_owner(user)
    args=query_args(owner,limit,offset)
    with conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            _assert_report_role(cur)
            cur.execute(query,args)
            names=[col[0] for col in cur.description]
            rows=[dict(zip(names,data)) for data in cur.fetchall()]
    return rows


def sol_summary(conn, trusted_dil_user, *, limit=100, offset=0):
    return _execute_readonly(
        conn,trusted_dil_user,SOL_SUMMARY_SQL,limit,offset)


def payment_details(conn, trusted_dil_user, *, limit=100, offset=0):
    return _execute_readonly(
        conn,trusted_dil_user,PAYMENT_DETAILS_SQL,limit,offset)


def sol_csv(conn,trusted_dil_user,*,limit=1000,offset=0) -> bytes:
    return csv_export(sol_summary(conn,trusted_dil_user,limit=limit,offset=offset),
                      SOL_CSV_FIELDS)


def payment_details_csv(conn,trusted_dil_user,*,limit=1000,offset=0) -> bytes:
    return csv_export(payment_details(conn,trusted_dil_user,limit=limit,offset=offset),
                      DETAIL_CSV_FIELDS)
