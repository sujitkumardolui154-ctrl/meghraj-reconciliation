# G69 deployment QA evidence register — 2026-11-05

## Source and environment
- Pinned artifact source commit: `1ff9658af246a66fdc3f467da403795b09abd1e0`.
- AWS Lightsail user-reported staging location: `/home/ubuntu/sbi-g69-staging`.
- This file records *user-supplied terminal output*, not an independently executed on-server attestation. Never treat a reported PASS as production approval.
- No credentials, customer rows, payment values, or private keys included.

## Passed or observed
| Gate | Evidence reported in conversation | Interpretation |
|---|---|---|
| Artifact ZIP | `unzip -t` passed; `sha256sum -c SHA256SUMS` returned archive OK | Artifact checksum passed on AWS |
| Source and platform | Provenance SHA matched pinned commit; Docker inspect `linux/amd64` | Pinned build inspected |
| Docker import | `docker load` succeeded; observed OCI/Docker ID distinction | Image imported for testing |
| Isolated Gunicorn | `RUNNING=true OOM=false NETWORK=none` and Gunicorn worker startup | Isolated startup passed |
| UI regression | `Ran 12 tests ... OK` | Local synthetic UI suite passed |
| Credit Note authentication | `Ran 13 tests ... OK` | Local synthetic contract passed |
| Login regression | `Ran 18 tests ... OK (skipped=4)` | 14 executed/passed; four **not tested** |
| Source integrity | `git cat-file -t e61b7f1` returned commit; `git diff --exit-code e61b7f1 HEAD -- dashboard_source/login.js dashboard_source/cloud_auth.py dashboard_source/dashboard_login_pages.py` passed | Three files unchanged from original commit |
| Historical auth fixtures | Original three files regenerated locally from `e61b7f1`, then 18-test login suite passed with 4 skips | Local fixture recovery; requires CI reproducibility |
| Container isolation | `NETWORK=none READ_ONLY=true PRIVILEGED=false MEMORY=201326592 RUNNING=false` | Restricted test container inspected |
| Anonymous HTTP | `/`, `/login`, `/dashboard.js`, `/api/reports`, and `/api/reports/reconciliation-changes` returned 401 in isolated Basic Auth preview | Anonymous denial only; no valid login proof |
| Existing services | Four SBI containers listed running; no published ports on G69 test | No disruption observed at inspection |
| Non-root test | Container created and Gunicorn worker boot reported, but effective UID and HTTP outcome not supplied | **Not yet verified** |
| Rollback | Container image/restart inventory command reported PASS; actual rollback not performed | Readiness only |

## Changes in draft PR
- Non-root staging image default UID/GID 10001.
- CI workflow rebuilds disposable image without push/deploy, verifies effective UID, no networking, anonymous denial, and disconnected financial flag.
- CI restores historical authentication QA fixtures from original Git `e61b7f1` and checks byte-for-byte comparison without changing tracked auth files.

## Mandatory unresolved gates
1. Review CI results; do not accept new workflow until green.
2. Four currently skipped tests: valid Firebase authentication, logout invalidation, session expiration/revocation, secure cookie flags. Test with verified mock boundaries and authorized private staging.
3. Financial parity against approved original 53-column source and report/credit-note contract, including conflict-group review, with zero financial DB writes.
4. Backup hashes, recovery permissions and actual isolated rollback rehearsal.
5. Explicit owner approval for production release; no automatic merge or deployment.

**RELEASE_STATUS=BLOCKED. Financial database writes=NOT_AUTHORIZED. Production cutover=NOT_AUTHORIZED.**
