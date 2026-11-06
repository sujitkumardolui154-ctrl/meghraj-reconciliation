# G69 independent release evidence and cutover checklist (2026-11-06)

Scope: Issue #72; coordination with Issue #43. This is an evidence checklist, **not** a release approval or a deployment script. Lightsail-first remains locked. PR #71 was merged on 2026-11-05; merge does not prove deployment.

## Gate 1 — Authentication (synthetic vs live)
- [ ] Verify the **exact proposed head SHA** and GitHub Actions URL; capture executed, failed, and skipped counts. Four lifecycle tests (valid Firebase login, logout/revoked replay, expired session, Secure/HttpOnly/SameSite cookies) must execute with verified offline mocks, not just have skip decorators removed.
- [ ] Verify all mandatory synthetic tests pass with zero skips; separately inspect negative authorization, cross-user, revocation, CSRF, cookie flags, and no-write evidence.
- [ ] Obtain **separate owner approval** and controlled environment before any real Firebase authentication acceptance test. Until then LIVE_AUTH=BLOCKED.

## Gate 2 — Financial source-to-report parity (read-only)
- [ ] Obtain independently approved original **53-column** source and ordered header contract, original SHA-256, worksheet name, record count and invoice identity rules. Do not substitute an exported 35-column report for the approved 53-column source.
- [ ] Obtain approved 18-column credit-note output and its SHA-256. Verify every row's invoice key, original source row, totals and Decimal arithmetic against approved rules. Record mismatched rows with old/new values and aggregate differences.
- [ ] Resolve or explicitly quarantine known duplicate/missing invoice groups and credit-note conflicts; do not silently choose an invoice or rewrite financial status.
- [ ] Record source and report fingerprints, expected and actual row counts, per-column header comparisons, independent reviewer, timestamp, and **financial writes=0**. If original evidence is missing, FINANCIAL_PARITY=BLOCKED rather than PASS.

## Gate 3 — Immutable backup and isolated rollback
- [ ] Obtain approved immutable snapshot/export manifest with object identifiers, sizes, cryptographic hashes and access evidence. Verify against independently recorded originals.
- [ ] Rehearse restoration **only on disposable, network-isolated synthetic staging**; record before/after hash, restore procedure, elapsed recovery time, error output and reviewer attestation.
- [ ] Keep the four active Lightsail containers, Caddy, production volumes, live Cloud Run and financial database untouched. No new paid resource is authorized. If safe isolated staging is unavailable, ROLLBACK=BLOCKED.

## Gate 4 — Release decision
- [ ] Verify non-root effective UID 10001 and isolated HTTP startup on the exact candidate image digest, not just Dockerfile USER or Gunicorn boot.
- [ ] Verify source provenance, exact-head CI, security controls, report schema parity, backup integrity, rollback evidence, live-auth acceptance and independent finance review.
- [ ] Present impact, rollback procedure, planned maintenance, zero-cost Lightsail-compatible alternative, any incremental recurring cost and explicit owner sign-off.
- [ ] Obtain **fresh change-specific owner approval** before PR merge, production routing, traffic cutover, live finance connection, IAM changes or financial writes.

## Reporting contract
For each gate report PASS/FAIL/BLOCKED/NOT_EXECUTED, exact commit, workflow URL, executed/skipped counts, evidence path/hash, reviewer and NEXT_GATE. A historical CI PASS applies only to the tested commit and scope. Any missing mandatory evidence blocks release. Do not treat source QA as live acceptance.

CURRENT_STATUS=RELEASE_BLOCKED
NEXT_GATE=INDEPENDENT_APPROVED_53_COLUMN_ORIGINAL_AND_BACKUP_EVIDENCE
FINANCIAL_WRITES=0
ARCHITECTURE_CHANGE=NONE
