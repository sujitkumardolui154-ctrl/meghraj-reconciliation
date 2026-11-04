# Stage 6R.2 — recovered backend package on existing AWS Lightsail

**Recovery input confirmed by owner:** `/home/ubuntu/sbi-recovered-source.oQyo43gQ`, stage 6R source inventory PASS. The recovered source is from **GitHub working code**, not the independently verified deployed Google Cloud Run image.

## Scope of this stage

Create a **disposable, isolated backend source package** reusing the already-built, previously approved local Stage 6D image `sbi-stage6d-candidate:c949777ffa32` as its base. Preserve all original `backend_source/` files for subsequent parity review. The entrypoint is intentionally an **inert compatibility shell**, not a live implementation of the financial backend:
- Static `GET /healthz`: reports source package ready, financial execution false, backend disconnected and Firebase unverified.
- All report, import, upload, monitoring, admin and financial routes: `503`; no source backend module imported.
- Bind HTTP to **127.0.0.1 inside a network-none container only**, with **no published host port**.
- Docker build uses **offline network mode**, `--pull=false`, and the existing cached base image; no pip install or remote resources.
- Run as non-root UID/GID 65534, read-only filesystem, cap-drop, no-new-privileges, bounded memory/pids.
- No Google Cloud Shell, no Firebase Admin credentials, no Firestore exports or SQL database and **no financial writes**.
- No existing Lightsail Docker service, Caddy route, AWS security group or GCP Cloud Run traffic is changed.
- A separate new local Docker image is created, then a disposable test container is **removed and verified absent**. Source copy in the owner's recovered directory is never overwritten. No EC2/extra server.

## Important gates

`BACKEND_SOURCE_PACKAGED` is **not** `LIVE_REPORTS_READY`. The source is coupled to Firestore and Cloud Run identity tokens. Exact production revision, Firestore data, Firebase identity, live financial report values and backup/rollback have **not** been verified.

This combined batch does **not** transfer or reconstruct money/payment data, nor validate financial results. Other migrations and production remain protected.

## Owner action

Run `staging/aws_lightsail/stage6r2_combined_backend_smoke.sh` after fetching an exact pinned GitHub commit into the working repository. Pass:
1. Local Git checkout with approved migration branch fetched;
2. Exact commit SHA;
3. Previously recovered source folder `/home/ubuntu/sbi-recovered-source.oQyo43gQ`.

The script archives a **temporary, pinned source copy** as build context, builds one image from the already available approved local Stage 6D image, runs an isolated, network-none HTTP smoke test, and cleans the temporary test container and archive. The new local image remains for subsequent isolated integration; it has no running service. No public inbound socket.

**Expected source/package-only result:** `PRIVATE_BACKEND_BUILD=PASS`, `STATIC_HEALTH_NO_FINANCE=PASS`, `REPORTS_DENIED=PASS`, `IMPORT_APPLY_DENIED=PASS`, `NETWORK_ISOLATION=PASS`, `CONTAINER_CLEANUP=PASS`, `BATCH_QA=PASS`.

**Next:** obtain authorized access to a trustworthy Firestore export (known earlier operation reportedly completed, but GCS object not reverified), confirm exact Cloud Run backend revision and Firebase Admin trust, test data parity using a reversible clone before any financial backend connection or production cutover.
