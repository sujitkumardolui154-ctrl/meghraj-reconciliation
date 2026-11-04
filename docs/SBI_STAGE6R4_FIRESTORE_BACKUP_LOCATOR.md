# Stage 6R.4 — recover Firestore export metadata without Cloud Shell

**Owner confirmed 2026-11-04:** Stage 6R.3 private AWS Lightsail monitoring compatibility `BATCH_QA=PASS`; four original non-financial routes PASS; network isolation, protected route denial and temporary cleanup PASS. Docker legacy-builder deprecation **warning** is not a failure and is not authorization to install new tooling.

## Grounded recovery evidence

- `backend_source/` and `dashboard_source/` have been recovered from the GitHub migration branch to `/home/ubuntu/sbi-recovered-source.oQyo43gQ`. The complete live Google Cloud Run revision has **not** been independently matched to this source.
- Original Firestore **full database export** was user-reported complete on 2026-11-01 around 06:29:09Z; exact operation ID and `outputUriPrefix` remain **unknown**. **Do not guess** that the known application upload bucket `meghraj-sbi-uploads-109590290120` is the export bucket.
- Connected Drive `DIL_MEGHRAJ_RECONCILIATION_DEPLOYMENT/06_DATABASE_BACKUP_VAULT` has 5 subfolders; all five returned zero files at prior check. A backup may still exist elsewhere (particularly GCS).
- Connected Drive `credit-note_snapshot-20261101T110857Z_manifest.pdf` confirms only a report reference: `baseline_rows=14374`, `unique_invoice_numbers=14360`, `full_schema_columns=53`, `credit_note_conflicting_unique_invoices=5`, `source_sha256=433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1`, `release_status=REVIEW_REQUIRED`. **A credit-note report manifest is not the full Firestore export**. Do not use it as a live-source substitution or clear outstanding duplicate/GST review.

## One combined AWS Lightsail offline locator

`staging/aws_lightsail/stage6r4_firestore_backup_locator.py` searches a bounded set of explicitly specified backup directories for Firestore export metadata *filenames* (never financial contents). It checks whether `gcloud` / `gsutil` executables are installed but never calls them or reads credential files. If the operator already has a **non-sensitive, authorized operation-status JSON file**, `--operation-json /path/to/operation.json` optionally validates the completed export status, exact project, documented export `@type`, and presence of `outputUriPrefix` without printing the bucket path. It **never** attempts a cloud API call.

Missing files/CLI are **not** proof the backup is missing from Google Cloud. Even a valid operation JSON is **not** proof the export objects still exist or can be read.

No IAM provisioning, service-account keys, external GCS transfer, Firestore write, AWS instance creation, Docker restart or production changes are performed.

The stage output intentionally separates `discovery_audit=PASS` from `recovery_gate=BLOCKED_PENDING_AUTHORIZED_GCS_EXPORT_AND_PARITY`. A successful inventory **never** authorizes a financial migration.

## Genuine GCS recovery once account access is available

Google Cloud Shell is optional. If the owner can authenticate to Google Cloud Console without Shell, open **Firestore → Databases → select database → Import/Export** to inspect recent completed export operation(s), including the export's **output URI**. Use Storage Browser to confirm the complete export files. Official Firebase docs: https://firebase.google.com/docs/firestore/manage-data/export-import

Alternatively, an authorized operator can use a separately approved Google Cloud CLI environment with **read-only IAM** and existing authentication; do not copy or transmit tokens, service-account JSON or certificate private keys to Lightsail.

If account login is unavailable, recover authorized Google project access first (including organization admin if applicable). No app, script or agent may bypass Google account access.

After export path and access are confirmed, verify export completeness, metadata, hash/row consistency, collection coverage, original 53-column schema, duplicate invoice conflict review and baseline reconciliation parity **before** any AWS database import.

**NEXT_GATE=RECOVER_EXPORT_OUTPUT_URI_FROM_GCP_OPERATIONS_OR_STORAGE**.
