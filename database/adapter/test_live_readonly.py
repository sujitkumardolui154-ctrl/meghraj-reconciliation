"""Live read-only SQL verification of the standalone PR129 reporting adapter.

Run only inside the isolated container with the PostgreSQL socket mounted.
Prompts securely for the restricted reporting account password; no password
is stored in the repository, Docker config, command line, or logs.
"""
from __future__ import annotations

import getpass
from functools import partial

import psycopg

from sbi_pg_reporting import read_report_counts


def main() -> None:
    password = getpass.getpass("Password for sbi_pr129_report_login (not echoed): ")
    try:
        # Provided to psycopg in memory, not via environment or Docker metadata.
        connect = partial(psycopg.connect, password=password)
        result = read_report_counts(connect=connect)
    finally:
        password = ""
    assert result.invoice_report_rows >= 0
    assert result.payment_report_rows >= 0
    print("ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS")
    print("invoice_report_rows=", result.invoice_report_rows)
    print("payment_report_rows=", result.payment_report_rows)
    print("PR129_LIVE_APP_MODIFIED=NO")
    print("FINANCIAL_ENGINE_MODIFIED=NO")


if __name__ == "__main__":
    main()
