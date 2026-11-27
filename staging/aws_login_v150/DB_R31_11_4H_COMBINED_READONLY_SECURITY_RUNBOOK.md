# R31.11.4H — Combined security QA in one read-only AWS command

**Stage:** R31.11.4H (combined R31.11.4E + R31.11.4G)
**Authorization:** QA read-only only. Source and offline mocked CI are NOT
proof of a real browser session or mutual-TLS connection.

## Recorded operator observations (27 Nov 2026)

The AWS operator reported R31.11.4G read-only preflight PASS:
- PG16 `sbi-r3114-private-postgres` on internal unpublished QA network,
- 0 import batches, 0 source rows, 0 payments, 0 statuses, 2 real owner maps,
- no R31.11 QA public Caddy route,
- Caddy config SHA-256
  `61d14b20bd57ce7ba4e6150324bddacefa186e5196b40c19fd57827907b0877b`,
- all 4F temporary candidate resources absent.

This reference hash is compared against the current Caddy config at the
start and end of the combined run. On mismatch stop for separate review,
never apply or restart Caddy automatically.

The operator reported 4F post-test cleanup PASS, but **not** the
`DB_R31_11_4F_REAL_SESSIONS=PASS_TWO_FIREBASE_UID_BOUND_TO_PG` or
two per-tenant session result lines. Therefore this script explicitly prints
`EVIDENCE_NOT_PROVIDED` for live session E2E even on an otherwise PASS.

## Combined checks in exact order

1. Verify source pinned SHA + clean detached Git checkout and invalid-name
   mTLS design template; enforce fixed QA DB/container/network identity.
2. Re-run 4E read-only source guard, preflight, forced-RLS policies,
   restricted LOGIN roles and two protected mappings.
3. Re-check two pre-approved existing Firebase test users with Firebase
   Admin SDK read-only lookups. No password login, no token issuance.
4. Recheck protected credentials' UID10001 and chmod 0700/0600 metadata
   via read-only `sudo stat`, not credential contents.
5. Confirm no 4E private API runtime is deployed.
6. Verify 4G private DB network, zero source rows and two existing maps.
7. Read/hash existing Caddyfile only; no QA route, SHA unchanged since 4G.
8. Verify 4F one-shot container, outbound network and temporary ADC absent.
9. Recheck Caddy config SHA and empty database a second time.
10. Report combined read-only PASS, while genuine two-user 4F E2E and
    HTTPS/mTLS explicitly remain unverified/not tested.

## AWS operator (after exact CI-tested SHA is confirmed)

```bash
BASE=/home/ubuntu/sbi-r31-11-4g/source
TARGET=/home/ubuntu/sbi-r31-11-4h/source
BRANCH=feature/sbi-r31-11-4h-combined-readonly-security-20261127
SHA=<EXACT_40_CHARACTER_CI_PASSED_SHA>

test -d "$BASE"
test ! -e "$TARGET"
git -C "$BASE" fetch origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p /home/ubuntu/sbi-r31-11-4h
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"

/home/ubuntu/sbi-r3114c-firebase-venv/bin/python -u \
  "$TARGET/staging/aws_login_v150/r31_11_4h_combined_readonly_security.py" \
  --source-sha "$SHA"
```

On STOP, do not repeat any role/database provisioning, create Caddy
certificates, repeat 4F credentials, or loosen permissions. Share only safe
status lines. The command itself performs NO Docker, PG, Firebase, cloud
network or financial mutations.

## Expected output on an unchanged environment

```text
DB_R31_11_4H_SOURCE_AND_QA_SCOPE=PASS_PINNED
DB_R31_11_4H_PRIVATE_PG16_RLS_AND_ROLE_GRANTS=PASS_READONLY
DB_R31_11_4H_TWO_REAL_FIREBASE_USER_RECORDS=PASS_ADMIN_READONLY
DB_R31_11_4H_SECRET_METADATA_AND_RUNTIME_ABSENCE=PASS
DB_R31_11_4H_QA_EVIDENCE_ROWS=ZERO_OWNER_MAPS_TWO
DB_R31_11_4H_CADDY=PASS_MATCH_PREVIOUS_4G_SHA256
DB_R31_11_4H_4F_TEMP_CONTAINER_NETWORK_ADC=PASS_ABSENT
DB_R31_11_4H_AFTER_QA_CADDY_AND_DATABASE=PASS_UNCHANGED
DB_R31_11_4H_COMBINED_READONLY_SECURITY=PASS
DB_R31_11_4H_REAL_FIREBASE_SESSION_E2E=EVIDENCE_NOT_PROVIDED
DB_R31_11_4H_EXTERNAL_HTTPS_MTLS=NOT_TESTED
DB_R31_11_4H_R3112=ACTIVE_QA_DESIGN_RELEASE_GATED
DB_R31_11_4H_FINANCIAL_APPLY=LOCKED
DB_R31_11_4H_PRODUCTION_RELEASE=BLOCKED
```

## R31.12 status

R31.12 has been moved into active **QA DESIGN** tracking
([Issue #216](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/issues/216)).
This enables source work, synthetic rule and integration QA and release
review, not production Apply or financially mutating integrations.

**No additional live mTLS test is possible or authorized in 4H:** no
owner-approved QA FQDN, DNS/issuer, client CA and certificates, external
listener, or external Caddy QA route has been approved. Prepare a separate
approval-gated design once these are specified. Repeating the 4F real-login
test solely to manufacture missing receipts is not part of combined mode.
