# SBI Reconciliation — Batch A4 isolated Credit Note staging activation runbook
**Date:** 2026-11-12 (IST)  
**Workstream:** SBI Reconciliation / Credit Note import  
**WS-LOCK-001:** No production changes, no financial writes, no release approval.

## Exact deliverable

The isolated WSGI entry point is **staging/sbi_cn_isolated_stage_app.py**. It is *not* included in production_gateway.py and is never instantiated unless the operator explicitly starts it with \`SBI_CN_ISOLATED_STAGE=1\`. It installs the actual dashboard_sessions.install_sessions(app), then registers the Credit Note read-only staging Blueprint. The handler is intentionally **offline/registry-disconnected**, so every uploaded record without a local format error returns REVIEW_PENDING_REGISTRY. This is NOT an actual DB parity or live authentication certification.

The production application does not expose the new route. No database client or financial writer is instantiated by the staging app.

## Approved private AWS staging rehearsal — not a deployment

**Preconditions:** Confirm the branch CI passes. Run only on a separately isolated AWS host/test namespace under the appropriate approved operator identity. Never alter the existing AWS containers, dashboard deployment, Cloud Run services, repository baseline, production traffic, financial database, or Firestore control documents.

From AWS, preserve the existing worktree and set up a **new, independent** directory. The following commands fetch the isolated code and create a new worktree; they do not modify the existing working files:

\`\`\`bash
set -eu
SOURCE=/home/ubuntu/sbi-aws-app
DEST=/home/ubuntu/sbi-cn-isolated-stage
BRANCH=feature/sbi-cn-future-import-guards-20261112
test -d "$SOURCE/.git" || git -C "$SOURCE" rev-parse --is-inside-work-tree >/dev/null
test ! -e "$DEST" || { echo "DEST_ALREADY_EXISTS_STOP"; exit 1; }
git -C "$SOURCE" fetch --no-tags origin "$BRANCH"
REV=$(git -C "$SOURCE" rev-parse FETCH_HEAD)
echo "FETCHED_STAGE_REV=$REV"
git -C "$SOURCE" worktree add --detach "$DEST" "$REV"
cd "$DEST"
python3 -m venv .venv
.venv/bin/python -m pip install -r dashboard_source/requirements.txt openpyxl==3.1.5
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_sbi_cn_isolated_app_e2e.py' -v
\`\`\`

Run only a **private, loopback-bound** service, with the financial database intentionally unconnected:

\`\`\`bash
cd /home/ubuntu/sbi-cn-isolated-stage || exit 1
SBI_CN_ISOLATED_STAGE=1 \
SBI_CN_STAGING_PREVIEW_ENABLED=true \
.venv/bin/gunicorn 'staging.sbi_cn_isolated_stage_app:create_app()' \
  --bind 127.0.0.1:18089 --workers 1 --timeout 30
\`\`\`

From another authenticated AWS terminal session on the same host:

\`\`\`bash
curl --silent --show-error -o /dev/null -w 'ANONYMOUS_HEALTH_HTTP=%{http_code}\n' \
  http://127.0.0.1:18089/healthz
\`\`\`

Expected: \`ANONYMOUS_HEALTH_HTTP=401\`. A 401 proves anonymous denial, **not** a successful Firebase login. Do not forward port 18089 publicly, open a Lightsail firewall rule, add a reverse proxy, grant user claims, or copy production credentials for this test.

Stop the isolated process with Ctrl+C after the local smoke check. The new worktree can be retained for further isolated QA without affecting existing containers.

## Outstanding real E2E prerequisites

1. Establish an authorized private HTTPS staging origin. The existing secure \`__Host-*\` cookies and CSRF origin allowlist are for approved dashboard domains; do NOT work around them with public HTTP or disabled CSRF.
2. Obtain a **separate** service account whose effective IAM permissions have been independently confirmed to permit only the required \`get\` document reads and no Firestore writes or database export/import. Do not treat \`SBI_CN_ISOLATED_STAGE\` or \`SBI_CN_STAGING_PREVIEW_ENABLED\` as IAM evidence.
3. Verify the original Invoice Details., PAYMNENT and Credit Note source inventories, identity-key encoding, duplicates, historical index coverage and immutable backup before index certification; five historical Credit Note conflict groups remain pending.
4. Test Firebase real login, role \`sbi_credit_note_import_preview\`, cookie revocation, CSRF, real index reads and 401/403/503 responses in the private TLS staging origin. These have **not** been tested live.
5. A later transactional writer must be separately designed and approved. It must atomically check uniqueness at apply time; the read-only preview can never approve an import by itself.

## QA results

- Branch-only GitHub Actions run with 18 validation + 2 invoice compatibility + 23 CSV/XLSX registry preview + 20 HTTP/index-preflight + 14 real-middleware/mock-Firebase tests = **77/77 synthetic tests**.
- No online Firebase session or live financial database connection was performed.
- \`REAL_DATABASE_CONNECTED=NO\`
- \`FINANCIAL_WRITES=NOT_PERFORMED\`
- \`PRODUCTION_DEPLOYMENT=NOT_PERFORMED\`
- \`PRODUCTION_CUTOVER=BLOCKED\`
