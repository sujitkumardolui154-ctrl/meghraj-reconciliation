# SBI Phase 1 — AWS immutable read-only report candidate
**Date:** 13 November 2026 IST. **AWS is the deployment target.** No GCP deploy, financial writes or public changes.

## Implemented
- The current AWS backend always returns 503 for reporting by design. This branch adds `backend_source/aws_readonly_snapshot_reports.py` and an opt-in, sealed source-report route in `backend_source/aws_readonly_reporting_app.py`.
- The new adapter reads CSVs only from a private operator-configured absolute directory. Each file must match an externally SHA256-pinned approved manifest; source hash, receipt, time validity (maximum 30 days), exact 53-/18-column headers, independent header pins, row counts, width and actual report SHA256 are checked before serving.
- Returned reports say `SOURCE_REFERENCE_ONLY`, `reconciliation_executed=false` and `financial_execution_enabled=false`. No reconciliation inference, no payment allocation and no database writes.
- Existing staging Basic authentication remains mandatory for `/reports` and `/reports/{kind}.csv`; anonymous users receive 401. A public Phase 1 release still needs independently verified real Firebase/session claims and per-report authorization.
- The five historic Credit Note conflict groups remain PENDING_REVIEW, so Credit Note export cannot be enabled without a separate independently approved resolution.
- No configured approved snapshot means the current 503 behavior stays unchanged; no secrets or CSV files are committed.

## Isolation
- The standalone `staging/aws_phase1_reporting/Dockerfile` packages only the sealed gateway plus snapshot reader and minimal Flask/Gunicorn dependencies, running UID 10001.
- The existing AWS `stage_release_root.sh`, Compose setup, dashboard, ingress and six running containers remain untouched.
- The root staging executor still requires current main SHA and expects 503 on authorized reports. It must NOT be used to deploy this feature branch or a newly enabled report adapter.

## Required independently approved manifest keys
- `schema=sbi-aws-phase1-private-snapshot/v1`, `release_class=REPORTING_ONLY`, `approval_status=INDEPENDENTLY_APPROVED`, `approval_receipt_id`, `source_sha256`, UTC `approved_at_utc` and `expires_at_utc`, and exact `reports` metadata.
- The flags `financial_writes_disabled` and `reconciliation_executed` must be true and false respectively.
- Each report entry needs `file` (exact kind.csv), `sha256`, `row_count`, `column_count`, exact `headers` array, `classification=SOURCE_REFERENCE_ONLY`.
- `SBI_AWS_REPORT_SNAPSHOT_DIR`, `SBI_AWS_REPORT_MANIFEST_SHA256`, `SBI_AWS_APPROVED_53_HEADERS_SHA256` and (for Credit Note) `SBI_AWS_APPROVED_18_HEADERS_SHA256` must be provided as separate operator-controlled pins. For other report classes a distinct pin is mandatory.
- Canonical header hash is SHA256 over JSON UTF-8 encoding of the exact ordered header string array with ensure_ascii=False and compact comma/colon separators.
- A manifest claiming independent approval is not actual evidence of independent approval; the user must verify source provenance, hashes, completeness and reviewer authorization.

## Phase 1 remaining
1. Identify actual current verified 53-column source and read-only report CSV snapshots on AWS; do not treat old Drive Excel backups or a 10,560-row OK subset as complete production parity.
2. Independently verify header contracts and value parity and approve a private SHA-pinned manifest; mount approved snapshots read-only in a separate localhost-only canary.
3. Validate real UI login/role claims, authorized report HTTP and CSV value parity, denials for anonymous/revoked sessions, network isolation and independent rollback.
4. Obtain explicit owner authorization for an exact AWS Phase 1 deployment candidate after all release gates pass. Credit Note conflicts and financial writes remain locked.

## Evidence
- GitHub Actions `.github/workflows/sbi-aws-phase1-snapshot-qa.yml` executed seven existing read-only backend tests plus fourteen new snapshot tests. This proves isolated source behavior, not live AWS application readiness.
- `AWS_DEPLOYMENT=NOT_PERFORMED`; `LIVE_REPORT_DATA=NOT_CONNECTED_BY_CI`; `FINANCIAL_WRITES=NOT_PERFORMED`; `PRODUCTION_CUTOVER=BLOCKED`.
