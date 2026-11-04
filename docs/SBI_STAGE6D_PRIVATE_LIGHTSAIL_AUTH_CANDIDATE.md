# Stage 6D — Lightsail-only private full dashboard candidate

**Owner migration control:** existing Lightsail is the only approved AWS target; no EC2, extra paid infrastructure, Google IAM change, financial database connection or production cutover.

## Implemented source
- `dashboard_source/stage6d_private_entry.py`: requires `SBI_STAGE6_AUTH_PROFILE=aws-private-staging`, valid exact HTTPS `SBI_STAGE6_AWS_ORIGIN`, `SBI_STAGE6_PRIVATE_ONLY=1`, `SBI_STAGE6_FINANCIAL_EXECUTION=disabled`, `SBI_STAGE6_BACKEND_CONNECTED=false`; otherwise quits with code 78 **without starting any listener**.
- `staging/aws_lightsail/Dockerfile.stage6d`: contains the real `dashboard_source/production_gateway.py` plus login/session/admin/report source and dependencies. Runs as UID 65534; the prior finance-deny guards remain active and `/api/*` / `/reports/*` return 503 in AWS staging.
- `tests/test_aws_stage6d_private_candidate.py`: synthetic startup, missing/invalid origin, backend guard and protected routes. CI does not run Docker or deploy.
- Firebase browser API key is **not populated**; `/auth/config` returns 503 unless explicitly configured. A private app being runnable is **not** a successful real Firebase login.
- Firebase Admin still requires trusted Google credentials; no WIF provider was enabled and no key file was created.

## Follow-up gated deployment plan (not authorized or performed)
- Inspect free RAM. Existing host is 909 MiB with no swap, so do not launch an extra always-on process without capacity evidence and owner approval of its temporary runtime.
- Build only a separate image (does not touch running services).
- Review Docker run flags: isolated name, `--publish 127.0.0.1:18085:8080`, read-only root, no privileged privileges, no host filesystem secret mount, no env-file secrets, no public Caddy route, auto-cleanup after controlled test.
- Test an unauthenticated browser login shell, origin rejection, session/CSRF, route denial, and no backend calls; then stop and remove only disposable test containers.
- Real Firebase Admin live session and user validation is still blocked on an approved **Lightsail-compatible, application-owned and keyless** Google identity design. Do not use the service-managed Lightsail role from the unrelated AWS account or an unapproved EC2 proxy.

**Safe offline package-gate check after image build:**
```bash
sudo docker run --rm --network none -e SBI_STAGE6_AUTH_PROFILE=aws-private-staging -e SBI_STAGE6_AWS_ORIGIN=https://sbi-stage6.13-232-241-221.sslip.io -e SBI_STAGE6_PRIVATE_ONLY=1 --entrypoint python3 sbi-stage6d-candidate:TAG /app/stage6d_private_entry.py --check
```
This command is an illustrative example, not runnable until the image is built with the actual TAG. It performs no network connection and does not start the service.

**Gate:** `SOURCE_CANDIDATE_READY` is not `FIREBASE_REAL_LOGIN_PASS`. Production remains `REVIEW_REQUIRED`.
