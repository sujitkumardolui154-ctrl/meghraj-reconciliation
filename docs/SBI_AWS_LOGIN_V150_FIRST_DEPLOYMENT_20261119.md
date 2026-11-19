# SBI Phase 1 — AWS login and original dashboard UI first

**Scope:** Port the former Cloud Run v1.5 login and dashboard frontend to the existing AWS Lightsail preview domain, not GCP deployment. Release reporting APIs one at a time in later workstreams.

## Existing vs new routing

- AWS public URL: `https://sbi-preview.13-232-241-221.sslip.io/` routes to Firebase-verified v1.5 login, then the original dashboard UI after session authorization.
- `/login`, `/login.css`, `/login.js`, `/auth/config`, `/auth/csrf`, `/auth/session`, `/auth/me`, `/auth/logout` go to the separate `sbi-login-v150-stage` container after explicit activation.
- `/pipeline`, `/api/pipeline/*`, `/api/priority-tasks*` remain served by the original `aws_lightsail-sbi-preview-1` with its separate existing Basic Auth.
- Read-only original HTML/JS is displayed; `/api/reports`, `/api/upload`, `/api/imports/*`, monitoring endpoints and administrative user creation return denial, and no financial database connection is created.
- No automatic public traffic changes. The new service is staged inside the existing private Docker network with no published host port. Activation changes only the bind-mounted Caddyfile, with an original backup and in-process reload/automatic rollback.

## What is not migrated yet

- Financial reports, invoices, credit-note export, reconciliation engine, write APIs, and any data parity QA (intentionally deferred).
- Master administrator creation flow (`/users` and `/api/admin/users`) remains disabled; it would modify Firebase accounts and requires separate authorization.
- Real Firebase login requires AWS identity-provider runtime configuration; an unconfigured login is never claimed functional.
- Existing Cloud Run service is not read or written by the AWS deployment process. Firebase Identity Platform is intentionally retained as the sign-in provider so prior user credentials and roles can be reused.

## Private prerequisites on the AWS host

Never place private keys or credentials in GitHub, this chat, shell command histories, Docker image layers or logs.

1. An authorized administrator supplies the existing Firebase project's **web API key** as one line `FIREBASE_WEB_API_KEY=...` in `/etc/sbi-aws-login-v150/login.env`, owned `root:root` with mode `0600`. The key is a client identifier, not a substitute for server credentials.
2. For actual Firebase Admin session verification and revocation checks, provide an owner-approved restricted service-account credential at `/etc/sbi-aws-login-v150/firebase-service-account.json`, owned `root:10001` with mode `0440`. Prefer keyless identity federation where possible; a JSON key should only be used if explicitly approved, with least privileges, audit and rotation.
3. Verify that `sbi-preview.13-232-241-221.sslip.io` is permitted for the existing Firebase authentication configuration and that the intended Firebase users have the approved `dil_dashboard` claim.
4. The release script refuses incomplete config. It never auto-creates secrets or displays their contents.

## Deployment — one AWS terminal, no reporting tests

Fetch the exact reviewed branch into a separate worktree; do not check out new source over the active `sbi-aws-app` workspace.

```bash
bash <<'BASH'
set -euo pipefail
REPO=/home/ubuntu/sbi-aws-app
DIR=/home/ubuntu/sbi-v150-login-first
BRANCH=feature/sbi-aws-v150-login-first-20261119
git -C "$REPO" fetch --no-tags origin "refs/heads/$BRANCH"
SHA=$(git -C "$REPO" rev-parse FETCH_HEAD)
test ! -e "$DIR" || { echo 'REVIEW_EXISTING_LOGIN_WORKTREE'; exit 2; }
git -C "$REPO" worktree add --detach "$DIR" "$SHA"
echo "SOURCE_SHA=$SHA"
sudo bash "$DIR/staging/aws_login_v150/deploy_aws_login_v150.sh" stage "$SHA"
BASH
```

`stage` builds a distinct Docker image and checks the local login page/CSRF/auth config/routes without switching public Caddy traffic. It stops immediately if Firebase runtime secrets are absent; this is expected and does not change the old preview.

Once the private credentials and permitted domain are independently verified and stage prints `AWS_LOGIN_STAGE=PASS`, the authorized operator runs:

```bash
bash <<'BASH'
set -euo pipefail
DIR=/home/ubuntu/sbi-v150-login-first
SHA=$(git -C "$DIR" rev-parse HEAD)
sudo bash "$DIR/staging/aws_login_v150/deploy_aws_login_v150.sh" activate "$SHA"
BASH
```

Activation compares the current Caddyfile against the known original; if custom changes exist, it blocks rather than overwrites. It also validates the new Caddy config, checks HTTP 200 `/login`, 303 `/`, 200 `/auth/config`, and preserved 401 for the old `/pipeline`. Public anonymous probes do NOT prove a real Firebase login; verify a real approved user separately in the browser.

## Rollback (public routing only)

```bash
bash <<'BASH'
set -euo pipefail
DIR=/home/ubuntu/sbi-v150-login-first
SHA=$(git -C "$DIR" rev-parse HEAD)
sudo bash "$DIR/staging/aws_login_v150/deploy_aws_login_v150.sh" rollback "$SHA"
BASH
```

The rollback restores the backed-up Caddyfile and reloads Caddy. It does not stop the original application, remove datasets, or change financial data.

## Acceptance statements

- `AWS_LOGIN_STAGE=PASS`: original v1.5 assets and secure-denial routes pass private container checks.
- `AWS_LOGIN_V150_PUBLIC_ROUTE=ACTIVE`: Caddy routed the AWS login UI; **not** proof of real Firebase login.
- After actual user sign-in, verify `/auth/me` returns approved identity, dashboard loads, logout invalidates session, `/pipeline` retains original Basic gate and financial APIs remain denied.
- `REPORT_QA=DEFERRED_BY_OWNER`, `FINANCIAL_WRITES=DISABLED`, `FINANCIAL_PRODUCTION_CUTOVER=BLOCKED`.
