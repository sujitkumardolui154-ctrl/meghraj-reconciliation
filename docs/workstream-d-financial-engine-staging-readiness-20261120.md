# Workstream D — Financial Engine staging readiness and manual corrections
Date: 2026-11-20
Tracking issue: #106
Status: BLOCKED_ON_CANONICAL_SOURCE (not deployed)

## Verified baseline (GitHub main, read-only inspection)
- Root README explicitly states that production Cloud Run backend/database source is absent and this checkout is not a standalone financial application.
- backend_source/payment_report_rules.py is a v1.4.2 read-only classifier; it is not the canonical approved payment allocation engine.
- Existing AWS application, Firebase login, Control Tower and report staging must remain unchanged. A connected cloud host runtime audit has NOT been performed.
- No live database, invoice/payment values, end-to-end parity or release authorization has been verified in this workstream.

## Mandatory manual recovery — BEFORE code/deployment
1. Read-only inventory last-known-good AWS container image IDs/digests, current running container names and ports, Caddy routes, secrets *names only*, volume mount names, backups and rollback instructions. DO NOT print secret values, private invoices or payments.
2. Read-only inventory GCP project meghraj-reconciliation in asia-south1: Cloud Run services and revisions/image digests, Artifact Registry image IDs, authorized source locations and database backup manifests. Do not change routing/IAM.
3. Compare origin of currently deployed financial engine and authoritative source with this GitHub main. Recover verified complete deployable source to **private staging** with source provenance and secret scan; never publish real financial rows or credentials.
4. Obtain approved master rulebook, SBI branch/SOL master and input/output schema; verify v2.18-v2.51 rule precedence and original 53-column header. Preserve original sheet values and text IDs.
5. Build a versioned deterministic regression fixture set with synthetic data; test same-SOL waterfall, partial/full receipt, SBISA/SOL 1, multi-month service periods, protected allocations, SUSPENSE, DNM-01, duplicate invoice blocks, Decimal TDS/GST, and idempotence. Flag unresolved exceptions rather than auto-reconciling them.
6. Run independent exact-hash original-source / report-value parity; prove zero unauthorized financial writes, authenticated private staging routes, backup restore and rollback.
7. Deploy only an isolated, zero-production-traffic staging candidate using an immutable image digest after validated CI, independent QA and reviewer approval. Maintain existing AWS baseline.
8. Request separate owner finance release review. Do not grant write permissions or production traffic without explicit approval.

## Fail-closed gates
- Canonical source unavailable -> NO BUILD/DEPLOY.
- Approved master/rulebook and full historical output contract unavailable -> NO FINANCE QA PASS.
- Source-independent parity unknown or unresolved critical duplicates/credit note conflicts/GST mismatches -> NO FINANCIAL RELEASE.
- No verified runtime image digest, current host backup and rollback rehearsal -> NO STAGING ACTIVATION.
- All production financial writes/import Apply/settlements and production cutover remain BLOCKED.

## Manual correction log
| Finding | Evidence | Corrective action | State |
|---|---|---|---|
| GitHub source incomplete | root README on main | Recover deployable canonical engine privately and verify image/source provenance | BLOCKED |
| Available payment module is classification only | backend_source/payment_report_rules.py on main | Locate complete payment allocator; do not extend classifier as substitute without rulebook review | BLOCKED |
| Live financial parity unknown | No independent production snapshot evidence obtained in this operation | Independent read-only hash/value comparison | NOT_RUN |
| AWS/GCP runtime and rollback not checked | No host/Cloud Run operator session in this operation | Authorized read-only operator inventory | NOT_RUN |

This document does not authorize deploying to a live environment and is not evidence that a deployment occurred.
