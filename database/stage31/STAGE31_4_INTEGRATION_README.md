# Stage 31.4 — Private Invoice/Payment Upload Integration Candidate

**STATE: PREPARED FOR ISOLATED TESTS; NOT A PRODUCTION DEPLOYMENT.**

## Boundaries

- Current production PR129 Workspace, Firebase session, Caddy and central PostgreSQL reporting remain unchanged.
- New Flask Blueprint \`stage31_4_private_preview.py\` is NOT registered anywhere in PR129.
- Even when deliberately registered by test client, it responds with 404 unless server configuration \`SBI_STAGE31_4_PRIVATE_ENABLED\` is explicitly true. In production it MUST remain false.
- When enabled inside isolated Flask test client, each request needs trusted server-side auth and CSRF callback results; missing callback -> 503; anonymous -> 401; invalid CSRF -> 403. Synthetic callbacks are **not evidence of real Firebase session parity**.
- Every \`apply\` endpoint remains HTTP 423 LOCKED even for simulated authorized users. There is **NO PostgreSQL write adapter** in this module. No financial credentials.
- JSON previews carry workbook SHA-256, source contract counts and review flags. Original invoice values and payment amounts are not returned.
- Invoice upload accepts exact approved 34/35/53-column workbook formats via pre-existing source parser; source-only duplicate checks are not production database uniqueness verification. Live \`source_row_id\` foreign key, branch_id, client_name and SOL mapping remain unapproved.
- New payment evidence header order is exactly \`Description, SOL ID, Credit Amount\`; all cells must be genuine Excel text. This 3-column template is **not equivalent to the historical PAYMNENT A–L bank extract**. No bank-date/source transaction identity is inferred or created. No payment ingestion occurs.
- Existing Firestore v1.4.0 upload logic is NOT reconnected and NOT assumed to be a central PostgreSQL writer.
- Exact rupee/paise conversion lives in Stage 31.3 candidate but is not executed against production data by this Blueprint.

## Stage 31.4 combined QA plan

1. Capture central financial table counts, hash of production Caddyfile and running release image/container ID.
2. Verify deployed report PostgreSQL role lacks financial INSERT/UPDATE/DELETE privileges.
3. Verify live public route security (login 200 and anonymous report/bulk 401) via local TLS/SNI route.
4. Download only approved revision-pinned source-code files from GitHub and verify their SHA-1 Git blob.
5. Run all 14 Stage 31.1, 15 Stage 31.2, 22 Stage 31.3 and 22 Stage 31.4 tests in an **isolated ephemeral** container from the exact SHA-256 image already backing the running PR129 release. Container settings: network disabled; no privileged access; read-only filesystem and source volume; non-root user, resource bounds; no environment secrets or DB mount; auto-remove.
6. Verify live source financial row counts, Caddy hash and running container image/ID unchanged.
7. Never promote the preview routes to live or grant database write privileges. Record NOT_PERFORMED for owner authenticated Firebase/browser UAT and real PostgreSQL ingestion tests.

## Remaining Stage 31.4 blockers

- Confirm source and route parity with **real** authenticated Firebase owner session under a separately isolated staging endpoint, with real CSRF handling. Do not allow HTTP headers or query parameters to impersonate a user.
- Approve mapping of duplicate \`Client Name\` and \`Branch Code\` columns to independently verified SOL/branch master.
- Resolve original \`PAYMNENT.\` bank transaction unique identity (date, bank row, source hash) and original Column I Credit.
- Implement and QA true PostgreSQL atomic ingestion with stage receipts, idempotency, source-row FK, failed insert rollback and rollback of partially ingested batches in a separate private environment.
- Obtain separate explicit owner approval to activate any central DB writes, then Stage 31.5 controlled production activation. \`Financial Apply\` and Master v2.51 remain locked and separately gated.

## Expected status vocabulary

\`STAGE31_4_PRIVATE_COMBINED_QA=PASS_OFFLINE_SYNTHETIC_ONLY\` only means the isolated test-client/source-contract QA passed. It does **not** mean Stage 31.4 authenticated staging release is complete, and it does not approve Stage 31.5 or financial database writes.
