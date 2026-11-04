# Stage 6 — Full Google Cloud Run to AWS application migration

**Status: SOURCE MIGRATION INVENTORY STARTED. NO APPLICATION CUTOVER.**

## Reference and scope
- Reference UI: Cloud Run `login-v150`; GitHub source `dashboard_source/production_gateway.py` plus `dashboard_source/index.html`, session/account/login modules, report and import adapters. **GitHub main is not proved identical to the deployed Cloud Run revision** until the image/commit is pinned.
- Existing AWS public preview: `staging/aws_lightsail/compose.yaml` builds the simplified `staging/railway_public` pipeline application. Its app explicitly rejects financial API requests. It is **not** the full reconciliation dashboard.
- Original financial/report backend includes `backend_source/report_api.py` with Google Firestore dependencies and existing source header assumptions; do not point unreviewed AWS code at live finance databases.
- Legacy AWS Stage 5E–5I read-only security, HTTPS, disposable storage and clone rollback evidence **does not** certify full feature parity.

## Critical engineering blockers in existing source
1. `dashboard_source/cloud_auth.py` uses Google identity-token fetching through Google ADC; AWS VM cannot be assumed to obtain trusted Cloud Run identity tokens. Choose audited workload identity federation or migrate backend authentication deliberately; no service-account key files.
2. Firebase session management and CSRF enforce hard-coded Cloud Run origins. For AWS staging, design an approved origin allow-list and ensure secure cookie domain/HTTPS and Firebase credential verification; do not disable session checks.
3. Reports, import review, reconciliation changes and credit note have separate authorization and finance safeguards. Preserve explicit roles, receipts, 53-column source header integrity, disabled Apply and write controls.
4. Firestore and backend Cloud Run endpoints require verified network, identity, permission and egress design. No direct financial production connection at Stage 6 source audit.
5. Compare the **actual deployed Cloud Run revision**, not merely latest GitHub source. Pin image digest/source SHA, inventory API routes, source assets, account/session behavior, imports, reports, credit note, DIL chatbot shell, backups and admin functions.
6. Do not mistake installed UI elements for backend functionality; only functional authenticated tests against isolated staging prove parity.

## Ordered migration implementation
1. **Stage 6A — Pin source and deployed image:** record Cloud Run revision, image digest and exact source commit, preserve approved backup and environment-key names (not values).
2. **Stage 6B — Build full dashboard image privately:** package `dashboard_source` and app dependencies; run without public route or finance connectivity; include production gateway only after authentication/env safeguards are adapted and validated.
3. **Stage 6C — Identity:** establish Firebase verified sessions, CSRF, role checks, AWS HTTPS origin and AWS-to-GCP service authentication without exposing private keys.
4. **Stage 6D — API adapters:** route monitoring/report/import endpoints to audited read-only mocks or controlled copies, preserving backend status semantics and financial write prohibition.
5. **Stage 6E — Feature parity:** compare full login-v150 routes/pages and files against authenticated AWS private staging with negative and expiry cases.
6. **Stage 6F — Data recovery:** validate isolated backups, consistent 53-column report and branch/SOL rules; verify migration/rollback plan without touching actual financial production.
7. **Stage 6G — Candidate promotion:** full independent QA, backup/recovery, staged traffic, rollback, explicit release authorization. Leave Cloud Run live until acceptance passes.

## Manual single-command Stage 6A read-only source audit
On AWS Ubuntu, use an existing pinned local checkout (the known release worktree is an earlier main revision and may differ from current GitHub):
```bash
cd ~/sbi-aws-app || exit 1
git fetch origin feature/sbi-stage6-full-gcloud-to-aws-migration-20261104 || exit 1
git show FETCH_HEAD:staging/aws_lightsail/stage6_source_migration_audit.py > /tmp/sbi-stage6-source-audit.py || exit 1
python3 /tmp/sbi-stage6-source-audit.py --repo "$PWD"
```
The audit only reports files and known migration dependencies from that local checkout. It performs no network calls, container changes or financial actions. A result of exit 0 **is not release approval**.

## Non-negotiable gates
- Existing Google Cloud Run dashboard unchanged and remains reference.
- AWS preview and existing staging containers unchanged.
- No financial write, production Firestore migration or public traffic change in Stage 6A.
- No skipping Firebase session, CSRF, role checks or Cloud Run backend authorization.
- Migrate full application before running repeat infrastructure QA.

**Official workstreams:** K — AWS Migration & Hosting, E — Deployment & Operations, G — UI/UX Engineering, M — Audit, Compliance & Security and N — Release Governance.


## Stage 6C — implemented source adaptation (not a live deployment)

- Exact HTTPS AWS origin policy in `dashboard_source/stage6_origin_policy.py`, enabled only when `SBI_STAGE6_AUTH_PROFILE=aws-private-staging`. An explicit, exact `SBI_STAGE6_AWS_ORIGIN=https://<approved-host>.sslip.io` must be provided through private deployment configuration. No wildcard origins or HTTP fallback.
- Existing Cloud Run origin allowlists are preserved **per endpoint** in default mode: Firebase session + CSRF, upload, and imports retain their prior rules.
- `dashboard_sessions.py` still verifies Firebase ID/session tokens with revocation checks and retains secure, HttpOnly, SameSite cookie settings; no alternate bypass authentication was introduced.
- `stage6_aws_guard.py` rejects any AWS profile lacking an approved origin, all unknown profiles, and every `/api/*` or `/reports/*` request in AWS private staging with HTTP 503. This intentionally blocks financial and monitoring backend calls, user-management writes and report retrieval until AWS-to-GCP credentials, role checks and independent acceptance are completed.
- Full source image remains a **package-only, non-runnable** candidate. `stage6b_build_guard.py` now requires both Stage 6C guard modules to be packaged.
- Offline synthetic tests exercise valid/invalid/missing origins, original Cloud Run compatibility, unknown profiles and denied AWS backend routes.
- **Not verified:** actual Firebase credential authority on AWS, origin domain provisioning, private AWS login flow, backend identity federation, authenticated end-to-end sessions, certificate rollover and financial/report parity. No running container, production traffic, Firebase account or financial database was changed.

