"""Read-only PostgreSQL reporting access for SBI PR129.

A *library*, not a Flask route. Add an authenticated route only after the
PR129 authorization and blueprint registration mechanism is reviewed.
No writes and no financial-engine integration are implemented here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReportCounts:
    invoice_report_rows: int
    payment_report_rows: int

    def as_dict(self) -> dict[str, int]:
        return {
            "invoice_report_rows": self.invoice_report_rows,
            "payment_report_rows": self.payment_report_rows,
        }


def read_report_counts(connect=None) -> ReportCounts:
    """Fetch only counts from the two approved reporting views.

    Relies on an already restricted report-only PostgreSQL login; no SQL
    identifiers are interpolated from request data, and the session explicitly
    sets the transaction to read-only.

    Supply ``connect`` as an injectable psycopg-compatible connector for tests.
    For production, install psycopg[binary] in a *new* container image.
    """
    if connect is None:
        import psycopg
        connect = psycopg.connect

    host = os.environ.get("PGHOST", "/var/run/postgresql")
    port = int(os.environ.get("PGPORT", "5432"))
    database = os.environ.get("PGDATABASE", "sbi_reconciliation_main")
    user = os.environ.get("PGUSER", "sbi_pr129_report_login")

    # libpq reads password from an environment secret (PGPASSWORD) or a
    # properly permission-restricted .pgpass; never embed passwords in code.
    with connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
        application_name="sbi_pr129_reporting_adapter_staging",
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SELECT COUNT(*) FROM sbi.invoice_financial_summary")
            invoice_rows = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM sbi.payment_financial_summary")
            payment_rows = int(cursor.fetchone()[0])
    return ReportCounts(invoice_rows, payment_rows)
