# R31.7 — Dedicated internal QA network recovery

**Date:** 25 November 2026 (IST)  
**Scope:** isolated payment-source QA only; no production database deployment.

## Incident evidence

The original owner AWS R31.7 runner stopped correctly with `STOP=QA_NETWORK_ISOLATION_FAILED`. Owner's read-only network inspection showed `sbi-synthetic-isolated-38-31` internal, single-network PostgreSQL `sbi-synthetic-postgres-38-31`, and two running application members, one being `sbi-r31-auth-private-qa`. That authentication container was not on the original R31.7 allowlist.

The owner then verified image revision `7a2298d93b6ace5977dc959acea3c7aa7c7ce4f0`, with read-only filesystem, no privileged flag, no public ports and no Docker/Postgres socket mounts. The same revision's GitHub staging script deliberately starts the auth service on `aws_lightsail_private_web` and attaches it to `sbi-synthetic-isolated-38-31`; this is consistent with authorized private Firebase auth staging. It remains **dual-network**, and therefore cannot be whitelisted in an exclusively isolated source-test network without changing the test's security premise.

## Reviewed resolution

The original shared R31 private-auth staging network and service are left **untouched**. The R31.7 owner QA runner now accepts an *explicit* `--dedicated-isolated-qa` profile that preserves its original default setting but switches only the synthetic Postgres **target**, private QA **credential directory** and strictly private **network** to:

- New internal-only network: `sbi-r31-7-dedicated-internal`
- New disposable container: `sbi-r31-7-dedicated-pg`
- New private credential directory: `/home/ubuntu/sbi-db-management/db-r31-7-dedicated`
- Source synthetic schema: `sbi_ft04g_clean_0e858f93`
- Owner QA schema-only clone: `sbi_r31_owner_qa_20261125`
- Existing independently pinned live app **image**, reused only to run ephemeral QA source-reader/writer processes; no live application service mutation

The `db_r31_7_dedicated_isolated.py` launcher prepares the new internal-only network, starts a new empty disposable PostgreSQL 16 container, seeds the existing FT04 **schema only** from its audited synthetic QA SQL, runs the existing owner-source/report QA against the dedicated profile, validates exact network membership, and cleans up only its own recorded Docker object IDs/labels and synthetic credential filenames. Its CI and host guard reject an already-existing dedicated network/container/credential directory rather than destroying or replacing unidentified assets.

The original owner QA runner still rejects unapproved dual-network participants; no allowlist exception for the R31 auth service is added. The dedicated profile permits **only its own single-network PostgreSQL member** before the ephemeral test applications start.

## Verified test

Successful [GitHub Actions run 45479859805](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45479859805). Key markers:

```text
DB_R31_7_DEDICATED_NETWORK_NEGATIVE_TESTS=PASS
DB_R31_7_PINNED_SYNTHETIC_SOURCE_IMAGE=PASS
DB_R31_7_SEPARATE_SYNTHETIC_FT04_SCHEMA=PASS
DB_R31_7_DEDICATED_NETWORK_ONLY_QA_PG=PASS
DB_R31_TWO_OWNER_SAME_SHA_PERSISTENT_QA=PASS
DB_R31_DUPLICATE_REPLAY_NO_NEW_WRITES=PASS
DB_R31_OWNER_FILTERED_SQL_AND_CSV_PARITY=PASS
DB_R31_7_AWS_DEDICATED_SOURCE_AND_REPORT_QA=PASS
DB_R31_7_DEDICATED_TEST_ASSETS_REMOVED=YES
DB_R31_7_DISPOSABLE_END_TO_END_DEDICATED_QA=PASS
DB_R31_7_DEDICATED_DISPOSABLE_CLEANUP=PASS
```

This demonstrates compatibility in GitHub's disposable Docker host, **not on the user's AWS host**.

## AWS operator preflight and execution

Execute only from a **separate clean Git checkout pinned to the merged reviewed commit**. Use a non-root host account with narrowly authorized `sudo -n docker` access. Do not run with `sudo python3` (the launcher intentionally refuses direct root execution), and do not disable Docker or database preflight checks.

```bash
# Verify the reviewed merge SHA and use a clean separate worktree:
cd ~/sbi-db-r31-verification-20261125
git fetch origin sbi-central-postgresql-main-20261121
git worktree add --detach ~/sbi-r31-7-dedicated-audit <REVIEWED_MERGE_SHA>
cd ~/sbi-r31-7-dedicated-audit

# Verify requirements before any Docker creation. Both names must be ABSENT.
sudo docker image inspect postgres:16-alpine --format '{{.Id}}'
if sudo docker container inspect sbi-r31-7-dedicated-pg >/dev/null 2>&1; then
  echo 'STOP=DEDICATED_CONTAINER_ALREADY_EXISTS'; exit 1
fi
if sudo docker network inspect sbi-r31-7-dedicated-internal >/dev/null 2>&1; then
  echo 'STOP=DEDICATED_NETWORK_ALREADY_EXISTS'; exit 1
fi
if test -e /home/ubuntu/sbi-db-management/db-r31-7-dedicated; then
  echo 'STOP=DEDICATED_QA_DIRECTORY_ALREADY_EXISTS'; exit 1
fi
if test ! -w /home/ubuntu/sbi-db-management; then
  echo 'STOP=PRIVATE_PARENT_NOT_WRITABLE'; exit 1
fi

# Only if all reviewed preflight conditions are met:
PYTHONDONTWRITEBYTECODE=1 python3 -B database/stage31/db_r31_7_dedicated_isolated.py
```

**Do not run when any STOP or REVIEW_REQUIRED message occurs.** The launcher additionally requires the locally cached `postgres:16-alpine` Docker image. It does not pull arbitrary images or create a second main business database. Use the GitHub-pinned source checkout; do not copy private bank workbooks, service credentials, passwords or Firebase tokens into ChatGPT/GitHub.

### Expected successful receipts

- `DB_R31_7_AWS_DEDICATED_SOURCE_AND_REPORT_QA=PASS`
- `DB_R31_7_DEDICATED_TEST_ASSETS_REMOVED=YES`
- `DB_R31_7_PRODUCTION_DATABASE_WRITES=NONE`
- `DB_R31_7_FIREBASE_REAL_OWNER_AUTH=NOT_TESTED`
- `DB_R31_7_RELEASE_STATUS=DEDICATED_ISOLATED_AWS_QA_PASS_ONLY`

The original `sbi-r31-auth-private-qa`, existing FT04 staging overlay, private web network, central database and Caddy routes remain untouched. Real authenticated owner Firebase acceptance is separately owned by PRs #201/#202, and does not become proved by this source-only QA run.

**Release:** `DEVELOPMENT_DEDICATED_QA_CI_PASS`. **AWS_HOST_PASS=NOT_YET_VERIFIED**, **PRODUCTION_MAIN_DB_MIGRATION=NOT_PERFORMED**, **RECONCILIATION_ENGINE_V2.51=NOT_CONNECTED**.
