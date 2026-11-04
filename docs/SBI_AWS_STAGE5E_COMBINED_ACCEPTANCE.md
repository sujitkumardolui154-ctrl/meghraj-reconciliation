# Stage 5E Consolidated Deployment Acceptance — read-only checkpoint

Exact dashboard workstreams: **K — AWS Migration & Hosting (K01/K02/K05)** and **M — Audit, Compliance & Security (M02/M05)**.

## Owner-verified synthetic results

On 4 November 2026 the owner executed restricted Caddy with UID 65534, read-only root filesystem, CapDrop ALL, minimal CapAdd NET_BIND_SERVICE, no-new-privileges and UID-owned tmpfs. Caddy /data, /config and /tmp writes passed; local 127.0.0.1:8080 synthetic HTTP returned STAGE5E_OK. An initial connection-refused before Caddy readiness was transient. No actual live service was replaced.

## Remaining stage acceptance matrix

| Requirement | Current position | Required proof |
|---|---|---|
| Persistent Caddy certificate/config storage | UNVERIFIED | Isolated named-volume test with correct nonroot ownership; restart to prove persistence and cert safe paths |
| Actual staged dashboard assets and routes | UNVERIFIED | Confirm /srv mount type and content provenance, localhost HTTP route tests against real asset copy |
| Authentication and authorization | UNVERIFIED | Authorized + denied real HTTP checks using safe session identities; ensure upload/import/apply denied |
| Rollback integrity | UNVERIFIED | Immutable image present, safe clone restore test and verified receipt before any deployment |
| Cloud Run login-v150 parity | UNVERIFIED | Enumerate original Cloud Run screens/backend endpoints and explicitly compare; AWS preview is NOT a full migration |

## Manual combined read-only inventory (single command)

```bash
cd ~/sbi-aws-app || exit 1
git fetch origin feature/sbi-aws-stage5e-hardening-preflight-20261104 || exit 1
git show FETCH_HEAD:staging/aws_lightsail/stage5e_combined_readiness.py > /tmp/stage5e-combined-readiness.py || exit 1
sudo python3 /tmp/stage5e-combined-readiness.py
```

This checks the four existing named containers and immutable rollback-image availability using Docker inspect only. It does not collect environment values, host mount source paths or application credentials, create/remove containers, expose ports or access finance. A PASS means **inventory only**, not release readiness. Do not merge or deploy based solely on it.

No change to the currently deployed AWS public preview, live Cloud Run dashboard, task queue or financial database is authorized by this audit.
