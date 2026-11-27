# DB-R31.13 — Consolidated Firebase to PostgreSQL tenant RLS security handover

**Status: READ-ONLY SECURITY HANDOVER CANDIDATE; PRODUCTION BLOCKED.**

This milestone is deliberately not a new authentication implementation.
The repository already includes the restricted PostgreSQL login adapter
(`r31_11_4_runtime_rls_adapter.py`), feature-flagged private Flask route,
and previous R31.11.4I real Firebase Test A/B -> private PG16 in-process
acceptance. The prior 4I result is a **local operator-reported receipt**,
not a cryptographically signed external attestation and not a live deployed
HTTPS session test. R31.12 independently reported successful two-user
Firebase private-session tests, but R31.13 does not manufacture or
retroactively sign a separate R31.12 receipt.

## R31.13 scope

The new `r31_13_firebase_pg_binding_acceptance.py` reuses R31.11.4H's read-only combined checks and verifies the original
R31.11.4I local operator acceptance receipt against its pinned source SHA. That audit
rechecks the separate internal-only QA PostgreSQL, exactly two approved
Firebase test identities and restricted role mappings, no populated
financial source rows, private mounted-secret metadata, no lingering
ephemeral 4F services, and unchanged Caddy routing. It also validates
the local 4I operator receipt and runs static sanity checks on the
runtime adapter, feature flags, trusted `g.dil_user` identity,
PostgreSQL `session_user` ownership binding, and read-only RLS queries.

The audit is designed to cause **no** changes to Firebase, PostgreSQL,
Docker, Caddy, DNS, TLS certificates or finance. Its success means the
previous private acceptance evidence is still internally consistent.
It does **not** initiate fresh live Firebase sign-ins or real HTTP requests.

## AWS operator action (after final GitHub CI green)

Use a clean detached worktree from the reviewed source. Do not alter
existing 4I/4J worktrees, prior receipt, QA roles, passwords or database.

```bash
set -euo pipefail
BASE=/home/ubuntu/sbi-r31-11-4i/source
TARGET=/home/ubuntu/sbi-r31-13/source
BRANCH=feature/sbi-r31-13-firebase-pg-binding-acceptance-20261127
SHA=<FINAL_CI_PASSED_FULL_SHA>
git -C "$BASE" fetch --no-tags origin "refs/heads/$BRANCH"
test "$(git -C "$BASE" rev-parse FETCH_HEAD)" = "$SHA"
test ! -e "$TARGET"
mkdir -p /home/ubuntu/sbi-r31-13
git -C "$BASE" worktree add --detach "$TARGET" "$SHA"
test -z "$(git -C "$TARGET" status --porcelain)"
/home/ubuntu/sbi-r3114c-firebase-venv/bin/python -B -u \
  "$TARGET/staging/aws_login_v150/r31_13_firebase_pg_binding_acceptance.py" \
  --source-sha "$SHA"
```

Only share `DB_R31_13_`, `DB_R31_11_4H_`, `DB_R31_11_4I_`,
`DB_R31_11_4J_` and `STOP=` codes. Do not share identity UIDs,
emails, bank rows, passwords, tokens, database secret files or
the full private receipt contents. Never delete a prior acceptance
receipt to force a clean run.

## Release decisions

- **R31.13 private Firebase-to-PG RLS evidence:** may be PASS upon the
  successful read-only AWS audit, with the limited meaning above.
- **Continuously deployed runtime path:** NOT APPROVED. The 4F acceptance
  used temporary in-process Flask clients and an ephemeral QA container,
  not a deployed externally reachable service.
- **Revoked/expired real Firebase sessions:** NOT TESTED.
- **External mTLS / HTTPS end-to-end:** NOT TESTED. A localhost-only TLS
  rehearsal (4J) does not constitute real external acceptance.
- **Production financial apply / invoice / GST / reconciliation writes:**
  LOCKED pending independent financial and release QA.

On any `STOP=` result, inspect read-only status only. Do not rerun
4A/4B/4C provisioning, reconfigure master UIDs, modify role grants,
or open the AWS firewall/Caddy route merely to pass QA.
