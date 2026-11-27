# R31.11.4G — External HTTPS/mTLS readiness (READ-ONLY QA DESIGN)

**Status:** SOURCE QA / PRIVATE AWS READ-ONLY INSPECTION. Not external
HTTPS/mTLS acceptance. This stage does not enable routes or alter Caddy,
Docker networks, firewall rules, certs, accounts or financial records.

## Already provided by the AWS operator
- 4F post-execution counts: import batches 0, source rows 0, payments 0,
  status rows 0, protected owner UID mappings 2.
- 4F temporary container, external egress network and temporary ADC
  directory absent.
- **Missing:** the 4F real Firebase session-to-PostgreSQL execution PASS
  lines. Cleanup PASS cannot substitute for real authentication evidence.
  Never rerun the 4F `--execute` command just to make duplicate evidence.

## R31.12 status reclassification

Owner explicitly requested removal from the quarantine *planning bucket*:
GitHub [Issue #216](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/216)
records **R31.12 = ACTIVE_QA_DESIGN**, permitting code/specification,
isolated nonfinancial tests and review. **Financial Apply remains LOCKED,
production writes and R31.12 deployment remain approval-gated.**

## Read-only scope of this step
- Exact pinned source SHA / clean worktree.
- Existing isolated PostgreSQL 16 QA container on exactly one internal,
  non-attachable network, with zero published ports.
- SQL `BEGIN READ ONLY` to ensure four QA evidence tables are still empty
  while the two existing approved owner mappings remain.
- Running original public Caddy container; SHA-256 of its unchanged
  existing config (never print the config), absence of candidate private QA
  endpoints, image/container names, and sample invalid mTLS hostname.
- Temporary 4F Docker resources and ADC directory absent.
- Existing Caddy example template remains explicitly design-only with
  deliberately invalid `qa-r311.example.invalid` hostname. This file
  **must not be deployed**.

## Commands
Use only the pinned commit SHA that passed the exact-head GitHub CI.

```bash
BASE=/home/ubuntu/sbi-r31-11-4f/source
TARGET=/home/ubuntu/sbi-r31-11-4g/source
BRANCH=feature/sbi-r31-11-4g-mtls-readonly-preflight-20261127
SHA=<FULL_CI_VERIFIED_40_CHARACTER_COMMIT_SHA>
test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4g
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
python3 -u "$TARGET/staging/aws_login_v150/r31_11_4g_mtls_readonly_preflight.py" --source-sha "$SHA"
```

Expected successful status:
```text
DB_R31_11_4G_QA_POSTGRES_NETWORK=PASS_PRIVATE_UNPUBLISHED
DB_R31_11_4G_QA_DB_ROWS=ZERO_OWNER_MAPS_TWO
DB_R31_11_4G_CADDY_EXISTING_ROUTE=PASS_UNCHANGED_DESIGN
DB_R31_11_4G_CADDY_CONFIG_SHA256=<SHA256_VALUE>
DB_R31_11_4G_4F_TEMP_RESOURCES=PASS_ABSENT
DB_R31_11_4G_MTLS_REFERENCE=DESIGN_ONLY_INVALID_HOSTNAME
DB_R31_11_4G_MODE=READONLY_PLANNING_NO_AWS_CHANGES
DB_R31_11_4G_4F_REAL_SESSION_RECEIPTS=NOT_VERIFIED_BY_THIS_AUDIT
DB_R31_11_4G_EXTERNAL_MTLS_HTTPS=NOT_TESTED
DB_R31_11_4G_R3112_QA_DESIGN=ACTIVE_RELEASE_GATED
DB_R31_11_4G_FINANCIAL_APPLY=LOCKED
DB_R31_11_4G_PRODUCTION_RELEASE=BLOCKED
```
If STOP, do not modify Caddy or credentials and do not rerun 4A/4B/4C.

## Separate approvals necessary for actual external mTLS E2E

1. Review a legitimate QA-only FQDN, its DNS and firewall exposure,
   a trusted *test* client CA and server TLS cert, certificate revocation
   handling, security monitoring and rate limits, Caddy version + syntax.
2. Independently approve private runtime deployment under a named QA FQDN,
   approved Origin, and network route; no currently approved hostname or
   CA material is assumed here.
3. Produce genuine two-account Firebase-to-PG execution receipts and
   verify HTTPS with valid client certificate, no cert, expired/revoked cert,
   wrong CA, anonymous requests, forged cookies/UID headers and role scope.
4. Independently verify existing public Caddy routes remain unchanged and
   rollback is tested; leave financial API locked. Do not touch production
   finance without an additional scope-specific approval.

**R31.12 ACTIVE_QA_DESIGN is NOT production release approval.**
