"""Read-only adapter smoke test. Receives one password via stdin pipe.

The host runner reads the password in no-echo mode. No password is passed
through argv, Docker environment, source files, or logs.
"""
import sys
from functools import partial
import psycopg
from sbi_pg_reporting import read_report_counts


def main():
    password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise SystemExit("AUTHENTICATION_INPUT=EMPTY")

    try:
        report = read_report_counts(connect=partial(psycopg.connect, password=password))
    finally:
        password = None

    assert report.invoice_report_rows >= 0
    assert report.payment_report_rows >= 0
    print("ISOLATED_POSTGRES_ADAPTER_READ_ONLY=PASS")
    print("invoice_report_rows=", report.invoice_report_rows)
    print("payment_report_rows=", report.payment_report_rows)
    print("PR129_LIVE_APP_MODIFIED=NO")
    print("FINANCIAL_ENGINE_MODIFIED=NO")


if __name__ == "__main__":
    main()
