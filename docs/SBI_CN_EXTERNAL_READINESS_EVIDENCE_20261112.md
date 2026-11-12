# SBI Credit Note — External Readiness Preflight
**Work date:** 12 November 2026 IST  
**Project:** SBI Reconciliation  
**Workstream control:** WS-LOCK-001; no production or financial write authority.

## Connected-source evidence reviewed

1. **GitHub.** Existing isolated branch \`feature/sbi-cn-future-import-guards-20261112\` holds read-only CN validation, preview, an offline standalone staging app, 77 previously passing local tests and a fail-closed one-run combined QA tool. GitHub Actions run \`43225753782\` passed at source commit \`801eb479e5f86b1dba6baca88550314632e601d1\`. It ran 77 offline tests + 9 new external-preflight safety tests (86 total), plus loopback HTTP 401/401/403. No actual cloud IAM or Firebase login test was performed. Latest source-level testing does **not** certify production deployment.

2. **Google Drive archive.** The SBI archive folder is \`https://drive.google.com/drive/folders/12IPKUpeXOlGMz_pnIEWy0RhigQFbOBpW\`. Its **06-Versioned-Backups** folder has two historical Excel artifacts: \`INVOICE_MEGHRAJ_EXPRESS_SBI_ORIGINAL_BACKUP_2026-10-28.xlsx\` and \`INVOICE_MEGHRAJ_EXPRESS_SBI_RECONCILED_WORKING_2026-10-28.xlsx\`. These are historical workbook references **not verified** as a current Firestore export, tested restore, source parity proof or full application backup. The **04-QA-Evidence** folder holds a 28 Oct reconciliation QA Excel file and an older controls-only release manifest. The **05-Deployment** folder was empty in the connected folder listing at review time; this is **not** evidence that deployments never occurred. Other locations, including a separately mentioned GCS export, were not independently verified.

3. **Existing archive documents.** The dated missing-records register and deployment evidence archive still flag live Firebase, IAM effective permissions, source/financial parity, authenticated backup recovery and five unresolved Credit Note conflict groups. Those statements are source inventory/evidence-gap descriptions, not automatically updated proof of all current systems.

## New tool

\`tools/sbi_cn_external_readiness_preflight.py\` runs from a source checkout. It verifies file presence, source boundary and clean Git worktree, whether a staging handler is explicitly offline, known evidence-file **presence only**, CLI availability flags and credential-configuration **boolean flags only**. It makes **no network requests** and never reads cloud credentials, source financial values, bank transactions, confidential reports or authentication tokens.

The tool generates a new chmod 0600 JSON QA report and refuses to replace an existing file. It never changes the backend, financial database, IAM policies, GitHub main, AWS containers, routing, Cloud Run, or storage objects. **Presence of evidence is never approval.**

## Combined AWS audit command — isolated execution, no deployment

\`\`\`bash
set -eu
SOURCE=/home/ubuntu/sbi-aws-app
DEST=/home/ubuntu/sbi-cn-external-preflight-v1
PY=/home/ubuntu/sbi-cn-isolated-stage/.venv/bin/python
BRANCH=feature/sbi-cn-future-import-guards-20261112
REPORT="/home/ubuntu/sbi-credit-note-qa/SBI_CN_External_Readiness_$(date +%Y%m%d_%H%M%S).json"
test -x "$PY" || { echo "QA_PYTHON_MISSING_STOP"; exit 1; }
test ! -e "$DEST" || { echo "EXTERNAL_PREFLIGHT_DEST_EXISTS_STOP"; exit 1; }
test -d /home/ubuntu/sbi-credit-note-qa || { echo "QA_REPORT_FOLDER_MISSING_STOP"; exit 1; }
git -C "$SOURCE" fetch --no-tags origin "$BRANCH"
git -C "$SOURCE" worktree add --detach "$DEST" FETCH_HEAD
cd "$DEST"
PYTHONDONTWRITEBYTECODE=1 "$PY" -B tools/sbi_cn_external_readiness_preflight.py --report "$REPORT"
\`\`\`

Expected terminal label: \`SBI_EXTERNAL_READINESS=LOCAL_SOURCE_PREFLIGHT_PASS_EXTERNAL_BLOCKERS\`; this proves only source-local safety checks. The report lists external gates as NOT_TESTED / NOT_VERIFIED / PENDING_REVIEW / NOT_GRANTED. All pending gates remain blocked.

## Nine external gates requiring additional independent evidence

| Gate | Status | Authoritative evidence needed |
|---|---|---|
| Real Firebase session login/revocation | NOT_TESTED | Private TLS staged session, controlled authorized sign-in, revocation test |
| Private HTTPS staging origin | NOT_VERIFIED | Isolated ingress, secure cookie/origin/CSRF attestation |
| Effective read-only Google Cloud IAM | NOT_VERIFIED | Authenticated service-account permission audit, resource-level/inherited grants, deny confirmation |
| Live Firestore reads | NOT_ATTEMPTED | Explicit owner-authorized read-only client to certified indexes, without writes |
| Invoice/CN/replacement index parity | NOT_VERIFIED | Approved source-key inventory, exact hashes, index completeness and duplicate decisions |
| Five historical Credit Note conflict groups | PENDING_REVIEW | Source-verified signed individual decisions |
| Payment importer and amount parity | NOT_TESTED | Complete original source and independent value-level reconciliation |
| Database backup and restore | NOT_VERIFIED | Immutable backup identity/checksum + actual isolated restore rehearsal |
| Production owner authorization | NOT_GRANTED | Explicit final release approval after all prerequisite gates pass |

No assumption that existing historical Excel backups can replace a live Firestore export, atomic writer uniqueness check or recovery rehearsal.

\`FINANCIAL_WRITES=NOT_PERFORMED\`  
\`LIVE_DATABASE_READS=NOT_ATTEMPTED\`  
\`PRODUCTION_CUTOVER=BLOCKED\`
