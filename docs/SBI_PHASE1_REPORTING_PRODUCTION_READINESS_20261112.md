# SBI Phase 1 — Reporting-only production readiness
**Work date:** 12 November 2026 IST  
**Scope:** Dashboard, Firebase login, read-only reporting, optional Credit Note preview.  
**WS-LOCK-001:** All financial database writes, allocations, imports, report-value edits and production cutovers remain blocked without an independently verified owner-approved release.

## Verified from connected GitHub

- \`main\` commit \`13727fcae5104267b2f6270224dc41c4bb0caae9\` contains dashboard gateway, Firebase session middleware, login UI, read-only Credit Note report blueprint and report API source.
- The separate \`feature/sbi-cn-future-import-guards-20261112\` branch adds Credit Note upload-preview/validation modules. The dashboard gateway, Firebase sessions, login pages and existing Credit Note report blueprint have **identical Git blobs** on \`main\` and this feature branch; the new CN import preview is **not** integrated into the production gateway.
- GitHub Actions run \`43012842580\` for \`SBI Reporting-Only Automatic Production Deployment\` finished with overall workflow success and source contract tests PASS, **but** the cloud auth, private GCS evidence verification and traffic promotion steps were SKIPPED. No production reporting release can be inferred from this green check.
- \`tools/sbi_reporting_production_gate.py\` requires independent, SHA-bound release evidence, real authenticated report HTTP, denied anonymous/revoked/expired sessions, rollback, report snapshot/header hashes, approved candidate revision and protected production identity.
- AWS read-only backend source scaffold \`staging/aws_backend_readonly\` reports /readyz=503 and protected report endpoints=503 until independently certified data access. This is not a ready reporting product.
- Historic credit-note disputes and financial import writes are **out of scope** for any Phase 1 financial action and remain separately BLOCKED.

## Phase 1 release components

| Item | Source status | Actual release gate |
|---|---|---|
| Dashboard and login | \`main\` files present | Verify actual live revision/image, real Firebase login and session revocation |
| Read-only reports | \`main\` source present | Verify read-only IAM, actual authorized GET/CSV, denied unauthorized GET, approved 53-column snapshot/value parity |
| Credit Note display/report | Existing \`main\` report blueprint | Verify current 18-column report, pending historic 5 conflict pairs shown as REVIEW_REQUIRED, no wrong classifications |
| Future Credit Note upload preview | Isolated feature branch only | Do not silently merge; separately verify staging role+CSRF, source mapping, independent database index completeness or keep disabled |
| Financial writes | Not authorized | Out of scope, locked |

## Execution sequence (one host inventory, then live deployment evidence)

**Phase 1A — AWS last-working-baseline evidence.** Do NOT swap images. Use the read-only tool \`tools/sbi_phase1_readonly_host_inventory.py\` from this branch, pointing at the current AWS application checkout. It checks exact working-source Git blobs against approved \`main\`, records running image IDs and status for SBI/Caddy/ingress containers (no environment secrets), probes only localhost /healthz and /readyz, then emits a new private JSON inventory. It will NOT mark production ready.

**Phase 1B — Live reporting-only canary review.** Before any Cloud Run traffic action, independently verify the currently deployed \`sbi-dashboard\` baseline, candidate immutable image + 0%-traffic revision, private staged HTTPS Firebase login, viewer-claim authorization, live read-only reports and exact-value/header parity, IAM deny for writes, and true canary-to-baseline rollback.

**Phase 1C — Owner release decision.** Only after all verification evidence is hashed and independently approved may the existing \`sbi-reporting-production\` gate evaluate a reporting-only candidate. Owner must authorize the exact source SHA, candidate revision and deployment scope. Do not manually bypass the gate or run \`sbi_reporting_production_promote.sh\` merely because source QA passed.

## Isolated AWS inventory command — no deployment

\`\`\`bash
set -eu
SOURCE=/home/ubuntu/sbi-aws-app
DEST=/home/ubuntu/sbi-phase1-readiness-20261112
BRANCH=release/sbi-phase1-readonly-preflight-20261112
REPORT="/home/ubuntu/sbi-credit-note-qa/SBI_Phase1_Host_Inventory_$(date +%Y%m%d_%H%M%S).json"
test ! -e "$DEST" || { echo "PHASE1_DEST_EXISTS_STOP"; exit 1; }
test -d /home/ubuntu/sbi-credit-note-qa || { echo "REPORT_DIRECTORY_MISSING_STOP"; exit 1; }
git -C "$SOURCE" fetch --no-tags origin "$BRANCH"
git -C "$SOURCE" worktree add --detach "$DEST" FETCH_HEAD
python3 -B "$DEST/tools/sbi_phase1_readonly_host_inventory.py" \
  --host-root "$SOURCE" \
  --cn-root /home/ubuntu/sbi-cn-combined-qa \
  --out "$REPORT"
\`\`\`

**Evidence interpretation:**
- \`AWS_MAIN_BLOB_PARITY=PASS\` says the selected working-tree source files match the GitHub blobs; **NOT** that the running container uses that source.
- Container \`IMAGE_ID\` proves only observed immutable Docker image identity; provenance still needs independent source/build attestations.
- Localhost \`200\` health shows a local endpoint is reachable, not authorized financial report access or parity.
- Cloud Run IAM, live login, full reports, backup restoration and production deployment are *not tested* by this command.
- If Docker access is missing, report \`DOCKER_METADATA=NOT_AVAILABLE_OR_NOT_AUTHORIZED\` without using sudo or changing privileges.
- Do not paste cookies, tokens, private report rows, .env values or credentials into chat or GitHub.

**Release decision for this source-only checkpoint:** \`PHASE1_READY_FOR_PRODUCTION=false\`, \`FINANCIAL_WRITES=0\`, \`PRODUCTION_CUTOVER=BLOCKED\`.
