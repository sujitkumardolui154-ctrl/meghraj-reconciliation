# SBI Consolidated Release Design — A–N

Status: DESIGN PREPARED / GITHUB REVIEW REQUIRED. This is not a production certification.
Source-of-truth: agent/task_queue.json (88 tasks: original A-F 50 + new linked G-N 38).

## Architecture and ownership
- Public HTTPS: AWS Lightsail Caddy -> Basic-authenticated isolated preview (working snapshot). Financial API routes remain 403.
- Real dashboard UI: static assets only in preview; do not claim real account management, reporting, or monitoring works without endpoint and role tests.
- Private read-only reporting: future service separate from finance engine, session-authenticated, least-privilege Firestore read rights, sanitized responses, role-level API deny tests.
- Work queues: bounded workers and job IDs, dedupe/idempotency, overload protection, cache keyed by source SHA+user authorization+report version; never cache sensitive report data across users.
- Financial engine: isolated from AWS preview, no write credentials. Reconciliation v2.51 and preserved v2.18 output require complete independent QA.
- GitHub: PR branches, reviewed changes, no private invoices/credentials in PUBLIC repository. Deployment pinned to immutable SHA.

## Release lanes
A. **AWS dashboard and nonfinancial UX:** source/asset QA, realistic session/auth lifecycle, navigation, read-only monitoring with authorized backend, concurrency tests, preview rollback. Deployment allowed only after integrated tests and rollback proof; existing preview can stay online.
B. **Reporting, branch/data quality and recovery:** original 53-header independent source, Firestore baseline, receipts, CREDIT NOTE conflicts, report CSV/ZIP totals, signed-in authorized and denied requests, snapshot restore rehearsal. Reporting-only promotion after genuine evidence.
C. **Finance and write-capable updates:** v2.51 engine financial tests (SOL, TDS, SBISA, DNM, waterfall), already-paid exclusions, exact v2.18 export, independent original snapshot, conflicting records review, atomic update/rollback and explicit finance release certification. No premature production label.

## Consolidated QA gates
1. Before coding, compare Git SHA, config, prior CI and saved test manifest. Reuse exact unchanged evidence; retest modified dependency paths and mandatory authorization/data controls.
2. Automated unit + synthetic integration for changed modules; real authenticated allowed/denied E2E only within private staging.
3. Build signed manifest: commit SHA, dependencies, requirements IDs, tests with verified exit codes, backup/restoration evidence, changed files, release lane, rollback commands and status.
4. Never mark COMPLETE for a command merely printed or a container just created; verify response, logs, data safety and independent evidence.
5. Fail closed on missing source, finance exceptions, absent roles, stale snapshot, broken rollback, or missing Docker image.
6. Production label rules: AWS_PREVIEW_OPERATIONAL only for observed HTTPS/auth/health; REPORTING_RELEASE_PENDING until private data and auth evidence; FINANCIAL_PRODUCTION_BLOCKED until lane C signoff.

## Outstanding blockers for consolidation
- AWS preview rollback image pruning: consolidated_release.sh now fails closed when source image is absent; needs proven reliable pinned-image lifecycle and rollback rehearsal.
- Real AWS auth and account session lifecycle not migrated; Basic-auth only supports isolated preview.
- Read-only reporting and supervisor backend access/roles not integrated on AWS.
- Source 53-column independent header evidence, original database baseline, private report manifest, five CREDIT NOTE conflict groups and other financial exception review.
- Finance engine certification and write-enabled Database Update contracts not complete.
- Agent task states: respect existing disabled automation settings; do not resume agents automatically.

## Acceptance / release manifest
- Branch and commit, report artifact SHA, source schema, current auth grant and least-privilege review.
- Exact test case list with PASS evidence, skipped tests with rationale, change-specific retests and independent release requirements.
- Backup image ID must be inspectable; rollback tested on the actual deployment revision before traffic promotion.
- AWS preview and Google Cloud financial production separated. All unverified areas must stay disabled.
