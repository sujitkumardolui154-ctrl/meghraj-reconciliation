# SBI Owner-Approved Deployment — Staged Release Control
Date: 2026-11-06  
Scope: SBI Reconciliation application. Approved by owner to **start the deployment process**, but owner-rule authorization does not itself prove financial ledger parity or grant production financial writes.

## Current verified state
- PRs #80, #81, #82, #83 have been merged into main. Their exact source tests were previously green.
- Owner has approved conditional method rules OWNER-RULE-01..03 without external business-rule cosignature.
- Original 35 invoice evidence fields, bank PAYMNENT A:L, 53-column ordered report schema and bank I=Credit remain immutable.
- Credit Note normalization fix is source-merged. It does not repair 24-column source financial discrepancies or prove an authentic approved 18-column export comparison.
- Full source/ledger/Cloud Run runtime parity is not established. Original invoice S numeric-zero versus blank-only eligibility precedence remains unresolved.
- Previous private-stage helper `staging/private_stage_deploy.sh` reuses the **existing production container image** and specifies `--ingress all`. It does not package this merged commit or verify finance isolation. DO NOT use this helper for the owner-rule release.

## Staged sequence
1. **Phase 1 — source-pinned preflight (this PR):** From exact GitHub head, independently run existing owner rule, marker, Credit Note and new package safety suites. Create an integrity manifest and artifact containing only eight approved Python/doc/test files; no private workbook or cloud credential. `SOURCE_PREFLIGHT=PASS_SOURCE_PACKAGE_ONLY` does NOT mean Cloud Run deployment occurred.
2. **Phase 2 — isolated runtime candidate (not yet authorized by evidence):** Pin a real container image digest built from the merged source; verify a dedicated staging service account with **zero financial write privileges**, IAM-authenticated-only access, restricted ingress and a separate staging service that never changes the production service or traffic. Make rollback evidence before any candidate apply. A GitHub CI source-only success cannot satisfy this gate.
3. **Phase 3 — application staging acceptance:** Verify actual authentication, read-only backend/report integration, approved 53-column output, 18-column Credit Note source-value parity, original SOL master provenance, bank-to-invoice payment ledger & historical allocations; no false OK, no duplicated credit, all conflicts review-only.
4. **Phase 4 — backup/recovery:** Verify independent full source/database snapshot, SHA256 manifest, isolated restore, integrity readback, rollback and timestamped receipts. Existing historic exports without an isolated restore are not enough.
5. **Phase 5 — controlled production release:** Only on independently verified Phase 2–4 evidence, owner-authorized production cutover with safe rollback. Never infer an existing source-code QA workflow is a deployed Cloud Run service.

## Explicit non-authorizations
- No production financial database writes, invoice settlement changes, cloud IAM grants or traffic redirection.
- No private bank row uploads to GitHub or Actions artifacts.
- No external signer required merely to repeat the owner's approved business rules; independent technical data-integrity validation remains compulsory.
- No reuse of a historical v2.18 output workbook as a fresh payment input.

`OWNER_RULES=APPROVED` | `PHASE_1=CI_IN_PROGRESS` | `PHASE_2_RUNTIME=NOT_DEPLOYED` | `FINANCIAL_WRITES=0` | `PRODUCTION_CUTOVER=BLOCKED`.
