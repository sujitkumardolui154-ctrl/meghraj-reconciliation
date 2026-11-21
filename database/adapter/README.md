# SBI PR129 PostgreSQL reporting adapter — isolated staging

This is an **unconnected Python library** for the established **single** PostgreSQL database `sbi_reconciliation_main`. It does not register a Flask endpoint, modify the running PR129 container, import data, or touch the separate Financial Engine.

## Behavior
- Opens a PostgreSQL connection as the restricted read-only role (`sbi_pr129_report_login` by default)
- Forces a read-only transaction (plus a read-only default session option and 5-second statement timeout)
- Returns counts from `sbi.invoice_financial_summary` and `sbi.payment_financial_summary`
- Does **not** accept arbitrary SQL or user-supplied table names
- Does not print or embed credentials; libpq can use `PGPASSFILE`, a properly protected `.pgpass`, or a managed environment secret

## Next required gates
1. Inspect exactly which six blueprints are registered in PR129 `/app/app.py` and where authorization is enforced.
2. Install `psycopg[binary]` only in a new **isolated staging** backend image; never pip-install into the running container.
3. Mount `/var/run/postgresql` read-only in the isolated staging test container, and supply the credential through a protected secret. Confirm query parity.
4. Introduce an authenticated API route **only after reviewing the existing Flask security chain**. Never expose the database directly to browsers, and never attach this reporting role to writes.
5. Preserve existing PR129 routes and disabled financial APIs. No live cutover without separate approval.

## Offline tests
Run `python3 -m unittest -v test_sbi_pg_reporting.py` in this directory. These are mock unit tests; not a real PostgreSQL integration test.
