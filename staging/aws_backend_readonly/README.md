# SBI AWS read-only backend packaging — SOURCE ONLY

This is a **non-deployed, isolated staging scaffold** for the next AWS backend
migration stage. It does not certify the reconciliation engine, read real SBI
invoices or move private financial data.

- The image copies only the sealed gateway app; **not** backend_source/main.py,
  uploader, importer, payment engine or Firestore writer code.
- Liveness: GET /healthz is 200 and reports financial_data_connected=false.
- Business readiness: GET /readyz is 503 until independent data certification.
- Allowed protected report routes: GET /reports and GET /reports/<approved>.csv.
  They require a separate operator-local Basic account with a >=24-character
  password and currently **always return 503**. No report data is returned.
- All writes and unrelated routes are rejected.
- Manual QA Compose is independent of the live AWS public-preview Compose.
  The credentialed backend has UID 10001, read-only filesystem, no volumes,
  NO published ports, and ONLY the internal Docker network. A separate
  uncredentialed non-root nginx ingress joins both the internal Docker network
  and a dedicated normal bridge and publishes only 127.0.0.1:18086.
  Docker 29 can silently fail to publish ports on internal-only networks.
  This ingress intentionally has no report credentials or financial data.
- GitHub Actions runs synthetic HTTP/deny tests and a no-network non-root image
  smoke test, but does not deploy.

**Do not run this image as production.** No new IAM, Firebase claims, AWS
credentials, automatic releases, financial writes or data copying is authorized.
Never add .env, passwords, cookies, database exports, customer records or tokens
to GitHub. Use independent credentials; do not reuse the AWS public preview
login. The existing AWS Lightsail preview, staging executor, Caddy, dashboard,
chatbot and financial database are left untouched.

Before any manual staging run, separately review the image source SHA,
least-privilege auth, private input evidence, 53-column report integrity,
rollbacks, read-only Firestore migration strategy and formal QA approval.
A green source test is not a deployment or financial release.


## Proposed approval-gated staging automation (not installed on AWS)

The GitHub Actions workflow
`.github/workflows/sbi-aws-backend-staging-release.yml`)
has two manual modes:

1. **preflight (default):** Verify that the full supplied SHA is the current
   `main` HEAD, run all synthetic contracts and build/smoke test the image
   without AWS connectivity or secrets. Nothing is deployed.
2. **stage:** After preflight, require the explicit confirmation string
   `APPROVE_ISOLATED_BACKEND_STAGING`, GitHub environment
   `sbi-backend-staging`, separate restricted staging SSH secrets and a
   validated `READONLY_V1` host executor. The executor fetches only the
   reviewed `main` SHA, builds the isolated candidate, probes it on
   127.0.0.1:18087 through an uncredentialed ingress companion,
   swaps only the backend+ingress staging pair on 18086,
   performs fail-closed checks, and attempts restoration of both previous
   staging images if post-swap checks fail. Nothing uses port 80, 443, 18081,
   18082 or the existing dashboard containers.

**Administrator bootstrap still required.** An independent operator must
review, then install root-owned copies of `stage_release_root.sh` and
`stage_ssh_gate.sh` as respectively
`/usr/local/sbin/sbi_backend_readonly_stage_release.sh` (0750)
and `/usr/local/sbin/sbi_backend_readonly_ssh_gate.sh` (0755).
The operator must configure a distinct unprivileged SSH account
`sbi-backend-deployer` with a **forced command** to the SSH gate,
no shell access, no forwarding, a tightly restricted single-script sudoers
entry, pinned host key verification, and a GitHub environment protected by
required reviewers. None of these host or GitHub settings has been performed
by this PR.

Use a **separate administrator-owned root:0600** credential file at
`/etc/sbi-backend-readonly/stage.env` containing **exactly two literal**
lines, `SBI_AWS_REPORT_USERNAME=...` and
`SBI_AWS_REPORT_PASSWORD=...` (24+ random characters). Do not reuse
existing preview credentials. No comments or shell code are accepted in this
file. Never paste credentials into GitHub, chats, action logs or version control.
The workflow expects only the dedicated secrets
`SBI_BACKEND_STAGE_HOST`, `SBI_BACKEND_STAGE_DEPLOY_KEY` and
`SBI_BACKEND_STAGE_HOST_KEY`. These **are not** the dashboard deploy secrets.

Do not configure any release secret or run stage mode until a human reviewer
has independently audited this executor, verified the isolated host setup and
exercised rollback. Staging remains monitoring-only: all report requests fail
closed with 503, and no actual financial engine/database is connected.
Production promotion and all financial write operations remain separately
prohibited. Google/Firebase reporting-role provisioning is dry-run only.


## Docker 29 localhost ingress correction (source-only, pending owner review)

The AWS canary evidence showed the backend itself started and responded to
`/healthz` inside the internal-only container (HTTP 200), while the same
published host port returned HTTP 000. The source fix keeps the backend
entirely on `sbi-backend-readonly-net` (internal=true, no published ports),
adds an uncredentialed nginx ingress on a separate standard bridge, and joins
only that ingress to the backend's private network. The ingress publishes
`127.0.0.1:18087` for canary or `127.0.0.1:18086` for staging.

Synthetic CI runs `test_localhost_ingress.sh` using disposable bridge networks
and synthetic Basic credentials; no AWS deployment or database connection.
The source adds pairwise first-install cleanup and restores BOTH backend and
ingress images during subsequent rollback attempts. The new executor responds
`SBI_BACKEND_EXECUTOR=READONLY_V2`; the GitHub stage workflow must reject the
previous V1 host executor. Before any stage run, an authorized administrator
must independently review and replace the installed root-owned executor, verify
its blob hash and safe permissions, then perform a status-only SSH check.
Do not replace host executors merely because a PR is green. An approval-gated
AWS staging release and independent real-host rollback QA are still required.
This does not enable finance reads, production reporting, DB writes or cutover.


## Owner-authorized automatic rollback rehearsal (source-only, pending review)

The deployed V2 executor already restores the old backend and ingress images
when a post-swap health gate fails. The original SSH allowlist does **not**
expose a way to trigger such a failure intentionally. The optional
`rollback-rehearsal` operation added here is permitted only when invoked
locally by an AWS administrator through the root-owned executor, **not**
through the dedicated SSH deployment account or GitHub Actions.

This is a potentially disruptive test **only for the separate localhost-only
staging endpoint** at 127.0.0.1:18086. It is never a financial, public-preview,
database, or production operation. Do not run it without the owner's explicit
staging-only authorization and a current healthy baseline.

The stdin request is exactly one line:

```text
rollback-rehearsal FULL_MAIN_SHA sha256:FULL_PREVIOUS_BACKEND_IMAGE_ID sha256:FULL_PREVIOUS_INGRESS_IMAGE_ID
```

Fail-closed gates require the reviewed SHA to equal current `main`, both
existing image IDs to match the operator-pinned baseline, both staging
containers to be running, and HTTP and authenticated deny-by-default baseline
checks to pass. All the usual limited source, network and credential checks
remain. The executor then builds and verifies a canary on 18087; after it
swaps the staging backend+ingress pair, it deliberately exits into the **same
automatic EXIT rollback trap** used for a real failed deployment. Both pinned
images must be restored, with health and authenticated report-denial checks
passing, for `BACKEND_ROLLBACK=PASS` and `ROLLBACK_REHEARSAL=PASS`.

A rehearsal can briefly interrupt **only** 127.0.0.1:18086. If recovery
fails, the test exits nonzero, reports manual intervention required, and must
not be retried blindly. Existing Caddy, public preview, 80/443, agent, dashboard,
invoice records and financial writes are out of scope. The release workflow
continues to accept only reviewed main-SHA deployments, never rehearsals.

**Do not assume this feature is installed on the AWS host.** This documentation
describes a proposed source change that must pass PR QA, be reviewed, merged,
and installed as exact verified root-owned executor bytes. Preserve the
existing V2 backup. Certify the actual rehearsal only from observed AWS
rollback outputs and independent container image/HTTP verification.
