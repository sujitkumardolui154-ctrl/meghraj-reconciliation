# SBI Development Module — QA reuse and deployment test selection policy

**Owner instruction adopted for this development branch:** Before running any deployment QA or integration test, check whether the identical test has already been implemented and successfully executed by another project module in GitHub. Reuse admissible evidence; execute only missing, failed, changed or environment-dependent checks. Never rerun an entire combined suite just because a module is renamed.

## Required pre-execution sequence

1. **Discover:** Search the connected GitHub repository across **Database Creation**, **Reconciliation Engine**, **Deployment Security**, Invoice/GST and other development branches, workflows, test files and run logs. Read the actual executed scope and source revisions, not merely a heading or PASS label. Check local restricted AWS acceptance receipts separately, without sharing their contents.
2. **Exact match:** Reuse a GitHub test only if the same workflow, pinned source SHA and source blob hashes are verified and its latest run for that exact SHA completed successfully. A newer failure invalidates prior success. Check that the test covers the same security behavior and relevant configuration. A test from another module is eligible only when these conditions hold.
3. **Source drift:** If test code, critical source or test configuration changes, run **only the mapped targeted QA** for that affected component and its direct dependencies. If an unknown code path or shared authentication/financial trust boundary changes, fail closed and request a full *relevant* regression, not a blind project-wide replay.
4. **Environment drift:** Revalidate environment-specific controls after credential, certificate, domain/DNS, Docker, Caddy, database roles, Firebase claims/identities, network or external Origin changes. Never infer an AWS live acceptance from a GitHub CI-only result.
5. **Safety failures:** A failed or canceled relevant workflow remains unresolved until reviewed or an authorized new passing targeted workflow supersedes it. Do not accept unrelated green workflows as fixes. A scanner flag can be a false positive, but requires review; it is not an authorization to disable security scans.
6. **Only necessary QA:** If an exact comparable CI PASS already exists, record `REUSE_EXACT_SOURCE_GITHUB_PASS` and SKIP the duplicate. If sources differ, record `TARGETED_SOURCE_QA_REQUIRED`; use the dedicated development workflow for that module. If source or GitHub evidence cannot be checked, record `GITHUB_EVIDENCE_UNVERIFIED` and **do not claim PASS**. The planner cannot invoke tests automatically.
7. **Final release gates:** Real external HTTPS/mTLS, client-certificate and Firebase-session revocation, actual two-tenant RLS via live QA ingress, backup/rollback and final financial release sign-off are separate evidence scopes. Prior synthetic TLS, metadata simulations, or private local in-process tests do **not** substitute for them. Financial Apply remains LOCKED until separately authorized.

## Separate QA development module

- `development/qa_reuse/evidence_registry.json` — pinned cross-module evidence with exact GitHub run IDs, tested source commit and blob fingerprint, assured test scope, known failures, and remaining external release gates.
- `development/qa_reuse/delta_qa_gate.py` — read-only source and GitHub status selector; does **not** dispatch tests, deploy infrastructure or alter financial data.
- `development/qa_reuse/test_delta_qa_gate.py` — focused offline unit tests for the policy.
- `.github/workflows/sbi-r31-14-delta-qa-reuse.yml` — targeted tests for the new policy only. Previous 4J/4I/4O/4P suites intentionally are not copied or rerun.

The existing invoice/GST-specific development QA selector is in the separate `feature/sbi-module-qa-reuse-policy-20261128` branch (`tools/qa_module_policy.py`). It has its own invoice groups and tests. This general deployment-security module **does not replace** that invoice-only selector or imply the branch was merged.

## R31.14 current evidence inventory (28 November 2026)

| Evidence | Admissible scope | Current known execution |
| --- | --- | --- |
| R31.11.4J | Real TLS socket protocol with disposable *synthetic* localhost certs | Exact-source GitHub PASS, reuse, no rerun |
| R31.11.4O | Domain-owner evidence form and offline checks | GitHub PASS for planning, no owner authority proof |
| R31.11.4P | PKI lifecycle and revocation metadata design simulation | GitHub PASS for design, no issued cert/revocation E2E |
| R31.11.4I / R31.13 | Genuine Firebase two-user private in-process PostgreSQL read-only RLS | Operator-provided AWS PASS/local receipt, **not** live external HTTPS |
| Private migration safety on R31.11.4P | Separate scanner | GitHub FAILURE, requires targeted security review |
| External mTLS and final production release | Real external endpoint, approved QA FQDN/cert/CA/revocation and signed release | NOT TESTED / BLOCKED |

**No real QA FQDN/domain registrar authority or certificate issuance was established in the source evidence checked.** The 4P plan explicitly records 6 PKI approvals and 8 lifecycle steps pending. The 4O evidence covers 6 domain approval gates; the earlier approval register has 23 outstanding approvals and the external test plan has 22 cases not executed.

## AWS read-only pre-execution command

From a clean pinned checkout of this branch after dedicated CI PASS:

```bash
PY=python3
SHA=<EXACT_REVIEWED_GITHUB_COMMIT_SHA>
ROOT=/home/ubuntu/sbi-r31-14-delta/source
test "$(git -C "$ROOT" rev-parse HEAD)" = "$SHA"
"$PY" -B -u "$ROOT/development/qa_reuse/delta_qa_gate.py" \
    --source-sha "$SHA" --check-github
```

This checks the public GitHub Actions evidence by **read-only GET**, with optional `GITHUB_TOKEN` already provided securely in the environment. Do not paste a token into ChatGPT or GitHub. If GitHub cannot be reached, STOP and verify independently; do not trigger duplicate full QA as an unverified workaround.

**The current feature branch only establishes a development QA policy and a next-step readiness plan.** It does not enforce required status checks on production/main until the owner reviews and integrates the policy into their deployment workflow. R31.14 live external acceptance remains blocked pending approval; all financial writes stay locked.
