# SBI A–N Combined Execution Plan

Status: DEVELOPMENT PLAN / REVIEW REQUIRED. Existing verified AWS preview is unchanged. Never label financial production ready without independent QA.

## Consolidated scope and priority
- **Wave 1 — AWS functional dashboard:** E, F, G, H, I, J, K, M, N. Preserve dashboard UI, DIL Intelligence Chatbot design, authenticated session requirements and all existing report surfaces. Develop account roles, authorized monitoring and chatbot read-only queries together in isolated staging. Use scoped read-only adapters; do not copy live private data into public GitHub.
- **Wave 2 — data/report certification:** A, C, L, M. Exact 53 positional headers, historical v2.18 export, consolidated CSV/ZIP, CREDIT NOTE and Reconciliation Changes, baseline and imports, duplicate/GST exception review, SHA manifest and restoration rehearsal.
- **Wave 3 — financial activation:** B, D, M, N. SOL-wide edits, audit receipts, atomic rollback, TDS/SBISA/DNM/waterfall engine and v2.51 release. Do not enable writes until independently verified.

## Preservation contract
Use existing approved chatbot components, gateway code, reports and UI before building replacements. Never replace a live application with a placeholder or override financial approvals. AWS local modifications to dashboard assets and login must be reviewed and synchronized first, without copying .env or financial records.

## Integrated implementation sequence
1. Reconcile active GitHub PRs #6, #12, #13 and source differences; no duplicate branches or repeated unchanged test runs.
2. Prepare a single versioned source manifest and reusable acceptance criteria keyed by Git SHA, feature IDs and test outcomes.
3. Implement modular adapters for authentication, read-only monitoring, approved reports, and chatbot using least-privilege credentials held outside public GitHub.
4. Run offline synthetic tests for auth role allow/deny, upload/import/apply denial, missing backend, report header consistency, chatbot privacy, rate limits, cache invalidation and Docker rollback.
5. Run private signed-in end-to-end QA only after independent private data/schema and role evidence exists; publish source-bound QA report and rollback receipt.
6. Deploy only the passing wave to private/zero-traffic staging; promote only with evidence and approval for its release lane.

## Acceptance gates
- Preview release: HTTPS/login/health and documented disabled financial APIs, confirmed working rollback.
- Reporting release: independent 53-header schema and private report manifest, Firestore baseline/import completeness, real role-based E2E, backup/rollback.
- Chatbot release: authenticated and permission-scoped, no unsupported financial decisions, bounded conversation/log retention, no model-driven database writes.
- Finance release: exact full engine/regression results, approved master and exception resolution, row/hash reconciliation, audited write/restore and explicit finance sign-off.

## Open blockers (not waived by user approval of consolidated design)
AWS local source differs from GitHub; actual AWS role-aware authentication and monitoring not connected; private source/header/credit-note evidence missing; outstanding financial exceptions; rollback image lifecycle not independently proven; full financial engine not certified.

## Execution tracking
All 88 tasks remain in agent/task_queue.json; linked G–N tasks are not new implementations of existing A–F modules. Never mark a task done merely because a command was printed or a Docker container started.
