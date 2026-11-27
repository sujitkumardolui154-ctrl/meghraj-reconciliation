# DB-R31.11.4D-2 — rollback-only cross-tenant RLS acceptance

**Scope: approved 2026-11-27 for `sbi_r31_11_4_auth_qa_20261126` in isolated container `sbi-r3114-private-postgres` ONLY.**

1. Run `r31_11_4d2_rollback_rls_acceptance.sh` from an exact SHA-pinned and clean Git worktree. The wrapper checks the private internal/closed Docker network, no published ports, currently empty QA evidence tables and two existing role mappings.
2. The SQL inserts two synthetic owner payment batches, two source rows, two payments and two source statuses **inside one uncommitted transaction**. It checks the pre-existing owner mappings but never changes or exposes them.
3. PostgreSQL 16 `SET LOCAL SESSION AUTHORIZATION` changes the `session_user` to each existing restricted LOGIN role. Both tenants must see exactly their own one row from each source table and the security-invoker view, not the other tenant. Both must fail to read the protected mapping table or INSERT evidence.
4. The SQL contains no `COMMIT`: it ends in `ROLLBACK`. On SQL error/disconnect the session transaction aborts. The wrapper re-connects and independently confirms all four evidence tables are empty; if not empty **STOP, do not manually DELETE**.
5. Existing QA LOGIN roles, mappings, and protected secret files remain unchanged. No Caddy, public access, runtime adapter deployment, password file reads or Firebase writes.
6. GitHub CI tests this against a **disposable PostgreSQL 16** with **CI-only fake Firebase UIDs**, including a deliberately permissive RLS policy to ensure the SQL fails closed. CI is not real Firebase or AWS proof.

**Limits:** This tests transaction-scoped, database-side RLS under each `session_user`. R31.11.4D already separately confirmed real private password-authenticated TCP logins. It does not test two different password-authenticated sessions querying committed records, Firebase session-to-DB binding, or external mTLS HTTPS end-to-end. Those remain pending.

**Production financial Apply LOCKED. R31.12 invoice/GST/reconciliation QUARANTINED.**
