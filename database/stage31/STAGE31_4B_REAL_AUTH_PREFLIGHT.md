# SBI Stage 31.4B — Real Firebase Auth / Upload Integration Preflight

**Dated 2026-11-23. PREDEPLOY SECURITY INSPECTION ONLY; NOT PRODUCTION ACTIVATION.**

## Evidence already approved

- Stage 31.3 maintenance-database synthetic PostgreSQL rollback QA passed (51/51 tests); no real financial writes.
- Stage 31.4 private preview + synthetic Flask authorization QA passed (75/75 tests); the candidate blueprint remains unregistered. Real Firebase and CSRF end-to-end tests were not performed.

## Stage 31.4B source checks and risk gates

1. Read **actual deployed** /app/app.py, /app/dashboard_sessions.py, /app/sbi_report_access.py, /app/pg_reporting_blueprint.py, using AST inspection inside the current PR129 container; print only boolean audit markers and source SHA-256, never code contents, credentials or cookies.
2. Verify global session install and Firebase \`verify_session_cookie(...,check_revoked=True)\`, user lookup and real CSRF Origin/header/cookie function are visible in deployed source. Static inspection is not a substitute for a real authenticated-user browser test.
3. Check that deployed \`ORIGINS\` includes the actual production URL \`https://pr129.13-232-241-221.sslip.io\`. Repo \`dashboard_source/dashboard_sessions.py\` still lists historical Cloud Run origins; **do not assume** it matches deployed production. If missing or policy is dynamically generated, mark review required; never bypass origin checks.
4. Run anonymous HTTPS GET checks against login (200), auth identity (401), PostgreSQL report summary (401), and bulk report status (401), using local Caddy SNI without transmitting credentials.
5. Read only PostgreSQL schema metadata, constraints and invoice indexes. Avoid reading any invoice or bank payment values. The \`sbi_pr129_report_login\` remains financially read-only.
6. Run the 75 approved Stage31.4 tests plus 21 new candidate binding tests isolated from network in a short-lived, non-root Docker container using the pinned image of the running PR129 release.

## Proposed staging-only Firebase callback

\`stage31_4b_auth_binding_candidate.py\` is **source code only**, not registered in the running application. The proposed read-only upload-preview guard checks \`g.dil_user\` and \`g.dil_identity\` populated by the real Firebase session middleware, exact UID agreement, owner/master policy, and a proposed separate Firebase claim \`sbi_invoice_intake_preview=True\`. It delegates CSRF to the real \`dashboard_sessions.csrf_valid()\`. Any missing claim is denied. That claim has **not** been granted, and the candidate cannot commit database records. Current private Apply always returns 423 LOCKED.

**Important:** The separate \`sbi_report_viewer\` report claim is insufficient for upload-preview authorization, and \`dil_dashboard\` alone is insufficient for financial write authorization.

## Owner read-only browser acceptance (after script inspection passes)

While signed in to the existing [production Workspace](https://pr129.13-232-241-221.sslip.io/), visit:

- \`https://pr129.13-232-241-221.sslip.io/auth/me\` — expected 200 for the **currently authenticated owner**, with \`administrator:true\` if the owner is a master account.
- \`https://pr129.13-232-241-221.sslip.io/api/reporting/v2/postgresql-summary\` — expected 200 and \`mode:"read_only"\` only for a session authorized to view this report.

In a private/incognito browser session with **no login**, the same URLs should report login required (401). Do not send session cookie, Firebase tokens, CSRF tokens, or passwords in chat or screenshots. Report HTTP status and allowed/denied only.

These browser checks **only verify existing production authentication/reporting**, NOT real private upload endpoints, which are purposely not deployed. Real POST CSRF and authenticated upload-preview must be QA-tested in an explicitly authorized, non-public staging environment after origin and role review.

## Mandatory release blockers after preflight

- Dedicated preview claim and actual owner session/CSRF POST parity review.
- Full original \`Invoice Details.\` 34/35/53-column source header, branch/client/SOL mapping and \`source_row_id\` FK design.
- Original \`PAYMNENT.\` bank transaction identity, original Column I Credit, bank date and immutable source-row identity; three-column evidence cannot prove settlement.
- Isolated full PostgreSQL transaction adapter for invoice/payment preview+apply; atomic receipt, deduplication, foreign keys, rollback, idempotency and report parity. No such writer is deployed.
- Owner's separate explicit approval after all final Stage31.5 release gates pass. The Financial Engine remains separately disabled.

**A \`PASS_INSPECTION_AND_OFFLINE_CONTRACTS_ONLY\` result does NOT imply complete Stage31.4B authenticated staging acceptance or authorization to turn on database writes.**
