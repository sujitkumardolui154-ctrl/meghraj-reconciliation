# DB-R31.11.4T — External HTTPS/mTLS Evidence Verification & Test Reuse
Date: 2026-11-28
Status: EVIDENCE REVIEW ONLY — NO LIVE EXTERNAL ACCEPTANCE, NO DEPLOYMENT

## Objective
Apply the cross-module "reuse exact verified QA, run only missing/changed checks" policy to the R31.11.4S external HTTPS/mTLS acceptance plan. Do not rerun 4H–4S combined private QA. Preserve production Caddy, PostgreSQL, Firebase, DNS, and financial-write locks.

## Canonical sources
- R31.11.4S acceptance matrix: `staging/aws_login_v150/r31_11_4s_external_acceptance_matrix.json` (22 external cases, all NOT_TESTED_EXTERNAL).
- R31.11.4S readiness: `staging/aws_login_v150/r31_11_4s_combined_external_acceptance.py` (read-only readiness, not an external test).
- Dedicated cross-module QA-reuse policy and checked-source planner (separate feature branch): `feature/sbi-r31-14-delta-qa-reuse-20261128`, `development/qa_reuse/QA_EXECUTION_RULES.md`, `development/qa_reuse/evidence_registry.json`, `development/qa_reuse/delta_qa_gate.py`.
- Do not imply the separate R31.14 branch has been merged into this branch.

## Live GitHub job evidence inspected 2026-11-28
| Case | Run ID | Job conclusion | Admissible scope | Decision |
| --- | ---: | --- | --- | --- |
| R31.11.4J synthetic mTLS | 45972166459 | success | Disposable localhost TLS handshake only | Candidate to REUSE after exact workflow, source-blob, and latest-run verification |
| R31.11.4O DNS evidence | 46004935631 | success | Offline domain-ownership evidence schema/design only | Candidate to REUSE for design scope |
| R31.11.4P PKI planning | 46121196969 | success | Offline PKI lifecycle metadata/simulation only | Candidate to REUSE for design scope |
| Private migration safety | 46121221654 | failure | Public source security scanner | TARGETED_REVIEW_REQUIRED |

GitHub job logs for the failed migration safety run show:
`BLOCKED: staging/aws_login_v150/test_r31_11_4k_external_mtls_readiness.py: potential secret; review locally`
`TRACKED_FILES=593`, `ISSUES=1`, `FINANCIAL_DATABASE_WRITES=0`.

This is a scanner flag, not a confirmed credential disclosure. Review flagged test literals and the scanner rule; do not disable or override checks without independent review. A later equivalent successful run on exactly the relevant source must be checked before declaring resolution.

## Evidence acceptance rules
1. Verify GitHub workflow name, run ID, executed commit SHA, conclusion, latest status for that source, and relevant source blob hashes against current candidate checkout.
2. If verified and unchanged, mark `REUSE_EXACT_SOURCE_GITHUB_PASS`; skip duplicate synthetic/design QA.
3. If changed, execute only affected source/security tests and direct dependencies. If unverified, mark `GITHUB_EVIDENCE_UNVERIFIED` and do not claim PASS.
4. Operator-reported 4I/13 private Firebase-to-PG RLS evidence is reusable only for its recorded private in-process test scope; not for external network assurance.
5. A failed scanner requires targeted review; unrelated green workflows cannot waive it.
6. No test can be marked `TESTED_EXTERNAL` without authenticated remote-client execution evidence, a matching QA endpoint configuration, and independent review.

## External test blockers — unchanged
- Owner-controlled approved QA FQDN, DNS/change authority, and reviewed firewall/ingress/rollback scope: PENDING.
- Actual approved server cert, client CA, client cert lifecycle and revocation enforcement: PENDING.
- Valid/invalid mTLS and SNI/hostname negative cases from an authorized external client: NOT TESTED.
- Real expired/revoked Firebase sessions and two-tenant PostgreSQL RLS via external HTTPS: NOT TESTED.
- Independent security acceptance and financial release sign-off: NOT GRANTED.
- 22/22 R31.11.4S cases remain NOT_TESTED_EXTERNAL in the baseline plan.

## Next targeted execution (no automatic dispatch)
1. Run the separate R31.14 exact-source GET-only evidence checker from a clean, SHA-pinned checkout (as documented in `QA_EXECUTION_RULES.md`). Capture only safe status lines; no credentials or owner-private receipts.
2. Review the isolated security scanner finding, specifically `test_r31_11_4k_external_mtls_readiness.py`; distinguish benign synthetic test fixtures from genuine secrets and preserve scanner effectiveness.
3. Obtain actual external QA environment approvals. Once independently approved, execute only the 22 required real external acceptance cases with matched evidence tickets and reviewer signoff.
4. Revalidate Caddy and QA PG postconditions; retain finance endpoint denial and rollback evidence.

## Invariants
`DB_R31_11_4T_MODE=READONLY_EVIDENCE_INVENTORY`
`DB_R31_11_4T_EXTERNAL_CASES_EXECUTED=0_OF_22`
`DB_R31_11_4T_EXTERNAL_HTTPS_MTLS=NOT_TESTED`
`DB_R31_11_4T_FINANCIAL_APPLY=LOCKED`
`DB_R31_11_4T_PRODUCTION_RELEASE=BLOCKED`

This document records a read-only GitHub evidence inspection, not a successful AWS run, actual HTTPS/mTLS test, production approval, financial write, or deployment.
