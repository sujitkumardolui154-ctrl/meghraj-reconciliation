# SBI Stage 6R.3 — Original static monitoring endpoints on private Lightsail

**Input confirmed by owner:** Stage 6R.2 on existing Lightsail `BATCH_QA=PASS`, `BACKEND_API_IMPLEMENTATION=NOT_CONNECTED`, `FINANCIAL_DATABASE=NOT_CONNECTED`, `FIREBASE_REAL_LOGIN=NOT_TESTED`, network-none and temporary-container cleanup PASS.

## Scope

This stage packages a *minimal safe compatibility adapter* on top of the locally built image `sbi-stage6r2-recovered:14115d966475` (the image created by the owner's 6R.2 pinned command). It does **not** run the actual Cloud Run production backend. Instead, it exercises the **original recovered** `backend_source/main.py` function for four allowlisted static/nonfinancial routes:
- GET `/health`: original source marker `financial_execution_enabled=false`;
- GET `/qa`: original source's `STATIC_BASELINE`, `PENDING` and `production_release=BLOCKED`;
- GET `/supervisor`: `STATIC_BASELINE`, `NOT_DEPLOYED` financial engine and release blocked;
- GET `/agents`: `DEMONSTRATION_ONLY` and no live agent connection.

The source uses `functions_framework.http` as a decorator. The lightweight private adapter temporarily substitutes only an identity decorator *during import* of pinned source, with no changes to that source or to production code. It verifies an explicit allowlist and the expected static result semantics. Do **not** use this adapter in production or claim it verifies the GCP deployed revision.

Every financial, report, credit note, import, upload, admin mutation and unsupported endpoint returns HTTP 503. A separate `/healthz` describes the private static test as **not connected** to Firestore or Firebase. The adapter does not load report/import modules or contact Cloud Run.

## Limits and safety

- Source archive pinned to an exact commit, not an assumed Google Cloud Run revision.
- Existing Lightsail host and previously approved local 6R.2 image only. No EC2, public port, new AWS service or internet in Docker build/run.
- Temporary container only, `--network none`, binds `127.0.0.1:8082` **inside** its network namespace, with no host port publishing, non-root UID, read-only filesystem, 128 MiB memory limit, minimal Linux capabilities.
- Temporary test container and archive cleanup verified. New local candidate Docker image remains for further explicit private integration only.
- No Google service account credentials, real Firebase authentication, Firestore database access, report parity, financial execution, production deployment or cutover.
- Existing Lightsail services, Caddy and original Cloud Run unchanged.

## Run (one combined command)

Use `staging/aws_lightsail/stage6r3_combined_monitoring.sh` from the pinned GitHub migration commit in `~/sbi-aws-app`, passing the Git working repository and exact commit. This is a **new** private test; do not rerun successful 6R.2 checks.

**Expected BATCH_QA=PASS** verifies four original nonfinancial routes, 503 denials for protected endpoints, startup gate, isolation and cleanup. It does **not** mean the full backend is deployed.

**NEXT_GATE:** recover/verify trusted Google Firestore export or original live data read permissions, finish keyless Firebase identity integration and perform authenticated financial report-value parity on a strictly read-only clone. Do not enable financial imports or public traffic without separate approval.
