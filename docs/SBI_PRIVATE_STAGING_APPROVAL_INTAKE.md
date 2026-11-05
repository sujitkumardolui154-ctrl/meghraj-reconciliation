# SBI Private Reporting Deployment — Stage Approval Intake

**Status on creation:** `REVIEW_REQUIRED`. This document is a checklist, **not** release approval and **not** authorization to deploy.

## Scope

- Candidate: `deployment/reporting_staging`, service `sbi-reporting-canary-v1`, region `asia-south1`.
- Private read-only reporting only; **no financial reconciliation execution, no database writes, no user traffic, no public access**.
- Main source SHA must be a Git commit's **40 hex characters**. An independently verified dataset SHA256 is **64 hex characters**. Never interchange the two.
- No source-controlled approval or manually invented PASS statuses.

## Evidence the independent reviewer must inspect (private; not committed)

- [ ] Approved baseline workbook/CSV with the exact 53 original columns, 14,374 baseline rows if the original historical snapshot is still authoritative, and independently verified source SHA256.
- [ ] Original headers independently confirmed in their exact order, not copied from the same generated code being tested.
- [ ] Firestore read-only baseline, imported-row and receipt integrity evidence, and evidence of snapshot freshness; discrepancies and duplicate invoice identifiers reviewed.
- [ ] Private 18-column CREDIT NOTE report, its verified SHA256 and count/conflict manifest, including resolution status for outstanding conflicts.
- [ ] Real Firebase login and entitlement tests against a dedicated non-admin test user; anonymous/expired/revoked/wrong-role access blocked.
- [ ] Verified deployment identity, WIF scope, protected `staging` environment, service IAM, explicit rollback command, and no financial mutation routes.
- [ ] Reviewed release source commit, signed/recorded evidence and reviewer identity; approval is limited to private zero-traffic staging.

A passed synthetic test cannot substitute for any of these real-data checks. Bank-payment allocation correctness and production approval remain separate gates.

## Safe intake process

1. Complete the independent QA checklist above, on a private machine/runner. Store sensitive data only in authorized private storage.
2. Protect the GitHub `staging` environment with required reviewers and a constrained deployment branch policy. Require a dedicated restricted staging service account.
3. After actual independent verification, store `REPORTING_APPROVAL_JSON` as an **environment secret of `staging`** (not in public repository files, issue comments, screenshots, pull requests or chat).
4. The approval must contain the existing gate's required fields: `release_scope=reporting_only`, `decision=APPROVED_FOR_PRIVATE_STAGING`, `source_sha` exactly the main 40-character commit SHA, `dataset_sha256` independently approved 64-hex data digest, non-empty `reviewer`, `private_evidence_verified=true`, `financial_execution=RESTRICTED`, `production_traffic_change=false`, `financial_database_writes=false`.
5. Only after the exact version of this fix is reviewed and merged: manually dispatch **SBI Autonomous Staging Deployment** on `main`. On push/PR, it performs only source QA. On manual dispatch, a separate protected `private-approval-gate` verifies the secret. Only `approved=true` may invoke the guarded `--no-traffic --no-allow-unauthenticated` candidate deployment.
6. Review the resulting workflow/job records, private canary login and report read tests, and rollback. Do not promote production traffic from this staging procedure.

## Current evidence status

```text
SOURCE_AND_SYNTHETIC_QA=PASS
PRIVATE_FINANCIAL_EVIDENCE=NOT_VERIFIED
REAL_FIREBASE_LOGIN=NOT_VERIFIED
LIVE_FIRESTORE_PARITY=NOT_VERIFIED
REPORT_VALUE_PARITY=NOT_VERIFIED
STAGING_APPROVAL=BLOCKED
ZERO_TRAFFIC_DEPLOYMENT=NOT_PERFORMED
PRODUCTION_CUTOVER=BLOCKED
```

### Process safety

This change fixes a Git-SHA length bug and moves access to the approval secret from unprotected source QA into the protected `staging` environment. The approval verifier does not create independent evidence by itself. Do not insert placeholder/fabricated values to satisfy it.
