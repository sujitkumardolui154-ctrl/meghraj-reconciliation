# SBI R5 — GitHub Actions Offline Docker Canary
**Date:** 23 November 2026 (IST)

## Objective
Run the R4 Payment Evidence application in an **ephemeral, network-isolated GitHub Actions container** rather than adding load to the existing 909-MiB Lightsail server. No AWS instance is accessed or changed.

## Reviewed scope
- Build Docker image from the checked-out development/PR commit; assert its exact source SHA label.
- Start one unique container with `--network none`, `--read-only`, UID `10001:10001`, dropped Linux capabilities, nonprivileged, 384-MiB RAM limit, 1-CPU limit, 128-PID cap and 16-MiB ephemeral `/tmp`.
- No port publishing, no bank/financial volume mounts, no AWS credentials, no Firebase credentials, no SBI master or private invoice records.
- Verify internal `/healthz` HTTP 200 with finance disconnected; login page HTTP 200; anonymous root redirect HTTP 303; unauthorized evidence GETs HTTP 401; unauthenticated payment, preflight, reconciliation and financial Apply POSTs HTTP 403.
- Exit trap deletes **only** the uniquely named test container and compares the original Docker container inventory. Separate `if: always()` postcheck fails if any R5 canary remains.
- GitHub token permissions limited to read-only `contents: read`. No `aws`, `kubectl`, registry image push or public ingress.
- Confirmed upload receipt cutoff: `2026-11-23T00:00:00+05:30`.

## What this does NOT certify
This CI canary tests isolated container startup and **unauthenticated** HTTP denial only. Real Firebase login/CSRF, customer-data uploads, verified bank date/UTR, live Lightsail network routing, 53-column financial writer parity, canonical complete v2.51/v2.39 implementation and financial posting remain **outside this gate**. The 3-column upload cannot prove authentic SBI transaction identity. R4 Flask mock tests remain separate evidence.

## Safety and approval
Development-only QA. Leave `main`, AWS Lightsail, Caddy routes, current 27 Docker services, and financial database unchanged. Financial Apply stays LOCKED. Do not merge to production, deploy a canary to AWS or authorize financial posting from this CI result. See .github/workflows/sbi-r5-offline-docker-canary.yml and scripts/ci/sbi_r5_offline_canary.sh.
