# SBI Railway public URL / protected preview

**Not the complete SBI application.** Public-facing login-protected placeholder only. No Firestore, Google Cloud, invoices, uploads, payments, backend proxy, or financial write paths. Do not treat this as financial-production release.

## Deploy manually with Railway
1. Create a Railway project from this GitHub repository, using branch `railway/public-login-staging-20261102`.
2. Set service **Root Directory** to `/staging/railway_public`. Leave other application services unconnected.
3. Before any deployment, add service variables `PREVIEW_USERNAME` and a unique random `PREVIEW_PASSWORD` of at least 20 characters. Set them in Railway, never GitHub source or chat.
4. Enable a generated Railway public HTTPS domain for this service.
5. Test `/healthz` returns only general status; homepage returns 401 without login and 200 with valid credentials.
6. Configure spending alerts and resource limits. Railway may charge above $5 included usage.

## Gate
No financial data or application source migration until sanitized source and approved database migration pass independent QA. Google Cloud production traffic and resources remain unchanged.

## Priority Monitor owner task editor (AWS preview, opt-in)
The project priority editor is **OFF** unless all three server environment variables
are configured: `SBI_PRIORITY_DB_PATH=/var/lib/sbi-priority/tasks.sqlite3`,
`SBI_TASK_OWNER_KEY` (random 32+ characters, different from preview login),
and `SBI_GITHUB_ISSUES_TOKEN` (fine-grained GitHub PAT scoped to this one repository,
with **Issues: Read and Write** permission only). Enter them into the server's
private `.env` or secret store, NEVER source control, GitHub Actions output, chat,
or browser JavaScript.

The AWS Compose service mounts a persistent, separate Docker volume named
`priority_task_db`. **Back up this volume before release or migration.**
This store contains only manually entered project task metadata; the financial
Firestore database, 92-item `agent/task_queue.json` and release gates are never
modified by this editor.

Preview login grants READ only. The separate owner key, same-origin request
and JSON API are required to create/edit tasks. The key is held only in the
current browser page's memory; users must re-enter it after reload. The GitHub
token stays server-side. Task creates/edits are published as public GitHub
Issues, identified by an immutable owner-task marker; existing unrelated
issues cannot be edited. If GitHub is down, an owner task remains saved in the
local database with `GitHub pending` (not success), with an explicit owner
retry action. Revision conflict returns HTTP 409.

This does not approve or bypass any mandatory release test, financial
reconciliation rule, production traffic switch or financial database write.
Do not enter private business or bank data into publicly mirrored task text.
A guarded AWS preview redeploy and real authenticated checks are still
needed before calling the feature LIVE. This editor does not run on the
isolated agent staging container unless intentionally configured with a
persistent volume and separate credentials.
