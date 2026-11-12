# SBI Credit Note — one-run combined remaining QA
**Run date:** 12 Nov 2026 (UTC 13:05, GitHub Actions run 43223883084)  
**Branch:** feature/sbi-cn-future-import-guards-20261112  
**Scope:** SBI Reconciliation Credit Note staging; WS-LOCK-001.

## Verified combined offline result

\`tools/sbi_cn_combined_remaining_qa.py\` executed successfully in GitHub Actions:
- 18 Credit Note validation tests: PASS
- 2 invoice import compatibility tests: PASS
- 23 registry and CSV/XLSX tests: PASS
- 20 HTTP authorization and index preflight tests: PASS
- 14 real dashboard middleware tests with **mocked Firebase**: PASS
- Total: 77/77 tests, no failures
- Source syntax and production gateway isolation: PASS
- Loopback-only Gunicorn smoke HTTP: anonymous /healthz 401; anonymous preview POST 401; untrusted origin POST 403; stopped temporary server
- Combined output: \`SBI_COMBINED_REMAINING_QA=COMPLETE_WITH_EXTERNAL_BLOCKERS\`

Actual Firebase login was not performed; no Google Cloud IAM permission check or live financial database connection was attempted.

## One combined AWS command (isolated, no change to existing app)

The existing AWS host has /home/ubuntu/sbi-aws-app and a QA virtualenv at /home/ubuntu/sbi-cn-isolated-stage/.venv. The following command creates a **new detached worktree**, never resets an existing worktree, uses the existing QA virtualenv, and stores an independently timestamped **QA-only** JSON report.

\`\`\`bash
set -eu
SOURCE=/home/ubuntu/sbi-aws-app
DEST=/home/ubuntu/sbi-cn-combined-qa
PY=/home/ubuntu/sbi-cn-isolated-stage/.venv/bin/python
BRANCH=feature/sbi-cn-future-import-guards-20261112
test -x "$PY" || { echo "QA_VENV_MISSING"; exit 1; }
test ! -e "$DEST" || { echo "EXISTING_QA_DIRECTORY_STOP"; exit 1; }
git -C "$SOURCE" fetch --no-tags origin "$BRANCH"
git -C "$SOURCE" worktree add --detach "$DEST" FETCH_HEAD
cd "$DEST"
PYTHONDONTWRITEBYTECODE=1 "$PY" -B tools/sbi_cn_combined_remaining_qa.py \
  --report "/home/ubuntu/sbi-credit-note-qa/SBI_CN_Combined_QA_$(date +%Y%m%d_%H%M%S).json"
\`\`\`

The runner:
1. Performs source syntax and gateway isolation checks.
2. Executes all five offline test groups (77 tests at source date).
3. Starts a temporary loopback-only Gunicorn application on a random local port; checks HTTP 401/403 behavior; stops it unconditionally.
4. Emits explicit external release blockers and a JSON QA report.
5. Does **not** authorize a merge, backfill, financial write, production cutover or live database connection.

The script reports \`COMPLETE_WITH_EXTERNAL_BLOCKERS\` and returns success only when all testable local checks pass. It returns a failure exit status on any locally testable failure. External blockers remain blocked in every case.

## External gates NOT testable with current offline setup

- Real Firebase login and revoked-cookie validation with a genuine staging session
- Authorized **private HTTPS** staging origin
- Independently verified read-only Google Cloud IAM effective permissions
- Live Firestore invoice, Credit Note and replacement index completeness
- Full historical source matching and independent certified source hashes
- Five unresolved historical Credit Note conflict groups
- New payment import implementation and independent invoice/payment financial parity
- Independent backup recovery/rollback evidence
- Owner production release approval

\`REAL_DATABASE_CONNECTED=NO\`  
\`FINANCIAL_WRITES=NOT_PERFORMED_BY_QA\`  
\`DEPLOYMENT=NOT_PERFORMED_BY_QA\`  
\`PRODUCTION_CUTOVER=BLOCKED\`

Do not describe this offline pass as completion of these external gates.
