# DB-R31.8 — Combined private Firebase / owner isolation / PostgreSQL privilege audit

**Prerequisite evidenced on AWS:** DB-R31.7 genuine Firebase password sign-in, session cookie, CSRF negative, synthetic Excel upload, isolated PostgreSQL source persistence, `₹118.00` JSON+CSV report parity, replay without double credit: **ALL PASS**. Current deployed container remains `sbi-r31-auth-private-qa`, pinned image `sbi-r31-auth-qa:7a2298d93b6ace5977dc959acea3c7aa7c7ce4f0`. No public Caddy route is configured and no production financial writes occurred.

## Single interactive combined QA (no deployment)

`r31_8_combined_security.py` reuses the previously passing R31.7 host safety preflight, verifies the actual Caddyfile has **no route to the private QA container**, and uses the same secure Firebase password prompt. It passes an ephemeral ID token to `r31_8_combined_security_incontainer.py` over Docker process stdin. No key, token, password, email or UID is printed. The container runs the existing immutable Flask app source; **no Docker image change**.

The in-container combined test:
1. Anonymous access to existing source upload / new PostgreSQL report routes returns 401; a made-up Firebase session cookie also returns 401.
2. Genuine Firebase user password session creates expected `__Host-` `Secure; HttpOnly; SameSite=Lax` cookies; no private identity fields are printed.
3. Server-side verified Firebase UID anchors owner context; a missing CSRF token or incorrect Origin for POST returns 403.
4. Creates **one disposable synthetic foreign-owner SQLite receipt row** inside the *already isolated QA evidence volume*, no XLSX file or bank data. Under the genuine Firebase administrator's session, the foreign receipt is invisible in the owned uploads list; GET and PostgreSQL sync both return 404; a client-provided `owner_uid` query or `X-Owner-Uid` header does not change the report.
5. Compares PostgreSQL owner-scoped SOL and row details before/after the foreign receipt test; they must be identical. **Finally deletes the disposable SQLite foreign-owner row even if a check fails**. No PostgreSQL payment or invoice data is inserted/updated/deleted by this milestone.
6. Inspects the SQL report role privileges: SELECT on the report view only, no raw table SELECT or finance INSERT/UPDATE/DELETE grants. Checks current QA database name and runtime role.
7. Inspects row-level-security catalog flags but **does not enable policy/alter financial tables**. Reports the known production blocker `PRODUCTION_RLS=NOT_ENABLED` if absent. Application-level filtering is not independently enforced DB tenant isolation.

**The test distinguishes:**
- `DB_R31_8_AUTHENTICATED_FOREIGN_RECEIPT_GET_SYNC=DENIED` is real signed-in user against a synthetic *foreign-owned receipt*; **not** a second genuine Firebase account signing in.
- `DB_R31_8_SECOND_REAL_FIREBASE_OWNER=NOT_TESTED` stays pending until a second independently authorized test user can sign in.
- `DB_R31_8_PRIVATE_HTTPS_EXTERNAL_E2E=NOT_TESTED_NO_PUBLIC_ROUTE` remains pending: the secure cookie and Origin checks use HTTPS `app.test_client` only, not external TLS/Caddy network transport.
- `DB_R31_8_PRODUCTION_RLS=NOT_ENABLED` is an explicit security *release blocker*, not success. Because the current QA report role can SELECT the global source view and relies on application owner filtering, do NOT promote it as a tenant-secure production database role.
- No v2.51 matching/allocations, financial writer, official SOL master approval, invoice data migration, or production rights are tested.

## Operator instructions

Run from an existing AWS checkout using a **clean SHA-pinned worktree** of branch `feature/sbi-r31-8-combined-security-20261125`. Example:

```bash
set -euo pipefail
EXISTING=/home/ubuntu/sbi-db-management/db-r31-central-catalog/source
TARGET=/home/ubuntu/sbi-r31-8-combined/source
BRANCH=feature/sbi-r31-8-combined-security-20261125
SHA=<PINNED_PR_HEAD_SHA>
git -C "$EXISTING" fetch -q origin "$BRANCH"
test "$(git -C "$EXISTING" rev-parse FETCH_HEAD)" = "$SHA"
mkdir -p "$(dirname "$TARGET")"
if [ ! -e "$TARGET" ]; then
    git -C "$EXISTING" worktree add --detach "$TARGET" "$SHA"
fi
test "$(git -C "$TARGET" rev-parse HEAD)" = "$SHA"
test -z "$(git -C "$TARGET" status --porcelain --untracked-files=all)"
python3 "$TARGET/staging/aws_login_v150/r31_8_combined_security.py"
```

The script requests an **existing Firebase dashboard-authorized account** email/password in the operator's local terminal, with a hidden password. Do not paste password, session, key or full UID into chat or GitHub. This runs **one** combined security test, not a repeated R31.7 payment import.

## QA acceptance outputs

Expect `DB_R31_8_PUBLIC_CADDY_QA_ROUTE=ABSENT`, anonymous and forged-cookie denials, real Firebase session, Secure/HttpOnly cookie flags, missing/wrong-Origin CSRF rejection, foreign-owner GET/sync 404, forged owner query ignored, private role grants, no PG writes and source-only status. Observe `NOT_TESTED` and `RLS=NOT_ENABLED` clearly; **do not interpret these as passed production security gates**. Any `STOP=DB_R31_8_...` requires follow-up and investigation before deployment.

## Remaining production work after this stage

Required distinct milestones before production promotion: (a) provision approved second Firebase test identity and test genuine tenant cross-auth scenarios; (b) implement *unforgeable* database-level tenant identity enforcement with direct global-view grants removed or properly secured, not a user-settable `SET app.owner_uid` GUC; (c) approve private HTTPS e2e routing and secure cookie forwarding with fail-closed Caddy route policy; (d) reconcile official SOL SHA and protected finance source imports, v2.51 calculations and writer in independent QA; (e) approve production database migration and rollback with explicit change control. Keep PRs stacked/draft and financial apply locked in all interim stages.

**Expected release:** `PRIVATE_COMBINED_SECURITY_QA_ONLY_PRODUCTION_BLOCKED` — private QA progress, no public deployment or financial release.
