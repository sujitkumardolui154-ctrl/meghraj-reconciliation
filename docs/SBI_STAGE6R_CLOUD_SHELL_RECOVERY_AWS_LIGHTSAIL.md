# Stage 6R — Cloud Shell unavailable: recover existing SBI app safely

## Source-of-truth recovery
Google Cloud Shell is a per-session disposable VM. Session expiry, or deletion of its user home directory after 120 days inactivity, is **not evidence** that an underlying Cloud Run service, Firestore database, Cloud Storage bucket or deployed container image was deleted. It is not the same as a Google account being revoked. Official docs: https://docs.cloud.google.com/shell/docs/how-cloud-shell-works

At commit `8edd92fc56972a676a03a967a1429c9a0cde140a` the migration working tree included 220 tracked source/config/test files (42 under `backend_source`, 22 under `dashboard_source`), including dashboard, sessions, report backend, import contracts, credit-note and AWS Stage 6 private Docker candidate. **Repository source is recoverable.** That is not proof of an exact match to the live Cloud Run image `login-v150` or live Firestore baseline.

An existing AWS Lightsail host and a private Stage 6D container were previously user-tested with 11/11 route security checks; they did not verify live Firebase, Firestore or report parity.

## External backup inventory
A connected Google Drive folder `DIL_MEGHRAJ_RECONCILIATION_DEPLOYMENT` was found, with `06_DATABASE_BACKUP_VAULT` subfolders. All five designated vault subfolders currently returned zero files in the connected Drive metadata check. **Not proof no backup exists elsewhere.** A prior operation reported a Firestore export completed around 2026-11-01 but its `gs://` objects and access have not been independently verified. Do not substitute old Excel reconciliations or static baseline data as if they are the live database.

## Recommended source-first migration

1. Pin and mirror the **GitHub branch/commit** independently of Cloud Shell, retaining Git history and approved source contracts.
2. Run `staging/aws_lightsail/stage6r_cloud_shell_independent_recovery.py` to check tracked source inventory and release blockers, without reading credentials.
3. Preserve existing Lightsail Caddy, Docker services and Cloud Run; keep the financial backend/API disconnected.
4. Package tested dashboard+backend source for a new isolated, temporary Lightsail environment. Verify exact required routes with synthetic data, no protected DB writes.
5. **Data recovery branch:** if Google Cloud Console account access works but Cloud Shell fails, inspect Cloud Run revisions, Artifact Registry images, Firestore database and Firestore export in Google Cloud Storage via an authorized operator. If Google account access is lost, use Google account/admin recovery. A third party cannot bypass IAM/restore project data without permission. Do not run noninteractive `gcloud auth login` on public Lightsail or upload personal credentials.
6. If the Firestore export is recovered, verify its operation metadata, project/collection coverage, SHA/row-level consistency where available, 53-column invoice contract, invoice IDs as TEXT, payment integrity and reconciliation reports **before** any database import to AWS. GCS Firestore export is not automatically a drop-in import format for another database; build explicit transformation with isolated QA and a rollback plan.
7. Firebase browser/API-key config is not Firebase Admin trusted server identity. Complete Stage 6D IAM, keyless auth, revocation and claims gate by explicit approval; no static Google service account JSON stored in AWS.
8. Obtain explicit separate owner approval for a non-financial private deployment, for identity trust changes, for financial migration and for public cutover in that order. Do not make EC2 or an additional AWS server a default.

## Stop conditions

`SOURCE_RETRIEVAL=RECOVERABLE_FROM_GITHUB`
`GCP_PRODUCTION_REVISION_PARITY=UNVERIFIED`
`FIRESTORE_BACKUP_RECOVERED=NOT_VERIFIED`
`FIREBASE_ADMIN_ON_LIGHTSAIL=BLOCKED`
`FINANCIAL_DATA_TRANSFER=NOT_PERFORMED`
`PRODUCTION_CUTOVER=BLOCKED`

The user is not required to have an active Cloud Shell **to reconstruct code** from GitHub. Full live state recovery requires an authorized database/backup source and credential trust; do not pretend this dependency is solved by code.
