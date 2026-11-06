# SBI Phase 2 — isolated Cloud Run staging runtime candidate

**Authorization:** Account owner requested Phase 2 deployment after completed owner-rule source QA, including PRs #80–#84 merged.  
**Stage 2A scope:** build and locally exercise a source-pinned **IAM-fronted canary**, with no bank/financial access; this is **not** a deployment of the reconciliation backend or dashboard.  
**Stage 2B:** external Google Cloud identity + registry + private Cloud Run provisioning remain separately gated.

## What is ready

- The container carries the **eight exact Phase 1 source-evidence files** via the validated SHA-256 release manifest. The source is included **for evidence**, not imported as a financial runtime.
- Source commit is embedded as a 40-character Git revision in OCI metadata and returned by `GET /healthz`.
- Python standard-library server with non-root UID/GID 10001, read-only container filesystem in the local CI run, no Cloud SDK, no database client, and **no finance input or export endpoints**.
- `GET /healthz` and `GET /release-evidence` expose safe sanitized runtime status.
- Financial/report/production paths return HTTP 503 and any mutation method returns 403.
- Cloud Run **IAM must enforce authentication**; the canary does not implement user-level authentication. Never expose it with `--allow-unauthenticated`.

## Deployment gates

1. GitHub CI runs source package integrity and local Docker runtime acceptance **without a Google Cloud deployment identity**.
2. Only a digest-pinned image built from this exact commit may be pushed to a **private** Artifact Registry. Record both Docker image ID and registry digest. A local image ID is not a registry digest.
3. The Google Cloud operator must verify: project `meghraj-reconciliation`, region `asia-south1`, caller authority, separate staging service identity, zero financial DB permissions (including resource-specific and inherited grants), no attached financial secrets, and an existing preserved production service.
4. Deploy **a different staging-only service** (never `sbi-dashboard` or `sbi-supervisor-backend`), with `--no-allow-unauthenticated`, `--ingress internal`, digest-pinned artifact and `STAGING_ONLY=true;FINANCIAL_WRITES_DISABLED=true;RECONCILIATION_EXECUTION_ENABLED=false`.
5. Verify actual Cloud Run revision image digest, service account, ingress, IAM and authenticated health/source response; confirm unauthenticated access denied, mutation endpoints deny, production service/revision/traffic unchanged.
6. The source-only canary cannot pass full application functional or financial acceptance. Reconciliation, Credit Note amount parity, allocation-ledger/official SOL provenance and isolated recovery testing are separate stages.

**Known caveats:** The existing `staging/private_stage_deploy.sh` reuses a production image with `--ingress all`; do **not** use it to represent this source build. Cloud Run service creation must not be inferred from a green CI check. `OWNER_BUSINESS_RULE_POLICY=APPROVED`; `CLOUD_RUN_RUNTIME=NOT_DEPLOYED_FROM_THIS_PR`; `FINANCIAL_WRITES=0`; `PRODUCTION_RELEASE=BLOCKED`.

## One-command Cloud Shell discovery and GitHub import

**This is the user's requested Phase 2B data collection, not a deploy.** The audit
is deliberately sanitized because the GitHub repository may be publicly visible.

```bash
cd ~/sbi-phase2-readiness
git pull --ff-only origin deploy/sbi-phase2-private-runtime-candidate-20261106
python3 staging/gcp_owner_private/collect_phase2_readiness.py --upload
```

This uses the existing authenticated `gcloud` identity to read the project,
Cloud Run services and stage IAM public-binding state, service-account counts,
Artifact Registry and enabled APIs. It NEVER uploads IAM principals, account
emails, tokens, secrets, URLs, environment variable values, invoices, bank
records, or entire raw GCP responses.

On success, the script outputs `GITHUB_SANITIZED_UPLOAD=SUCCESS` and a link
to a newly pushed **`audit/sbi-phase2-gcp-readiness-...`** branch. If the
GitHub CLI is authenticated, it also opens a **draft** pull request for review.
If not, the link opens the GitHub compare/PR screen. Upload is confined to a
single sanitized JSON file in `audit/cloud/` on that new branch; it **does
not** commit to `main` or the deployment branch. It makes no GCP changes.

The sanitized JSON remains locally saved in
`~/sbi_phase2_private_inventory/` with restrictive file permissions even
if GitHub push fails. If GitHub access is missing, authenticate directly in
Cloud Shell using your approved GitHub login workflow—never paste a PAT or a
cloud credential into a chat or repository.

Passing the collector does **not** verify inherited Firestore/IAM financial
write privileges or actual live authorization, and it does not perform
any deployment, registry push, financial data read or production cutover.
