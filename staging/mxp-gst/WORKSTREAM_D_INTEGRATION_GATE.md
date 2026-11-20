# Workstream D → MXP GST v2.7 integration and staged deployment gate
Owner instruction: 2026-11-20 · Issue #106 · Source PR #108 (merged)

## Proven baseline
- GitHub main now contains `staging/mxp-gst/`: read-only v2.7 matching rules, private-master dependency, fixed 16-column GST contract and synthetic alias tests.
- This is not a complete GST invoice-preparation engine or an integrated financial application.
- Finance canonical service provenance, private branch master/runtime, original invoice evidence, actual AWS source image and private Firebase routes are not verified by this PR.

## Stage sequence (all gates remain closed until evidenced)
1. Source-contract QA on this PR head: `python -m unittest discover -s staging/mxp-gst/tests -p 'test_*.py' -v`. Include the new Workstream D negative/contract tests; record exact head SHA and result. Source CI run is not asserted here.
2. Independently reconcile v2.7 against latest owner-approved prompt versions and rulebook precedence. The 16-column contract must be confirmed, and invoice values must be derived from authenticated original invoices, never fabricated.
3. Recover the canonical pre-existing Financial Engine and preserve existing allocations/statuses. Map the GST-only module as a separate non-mutating service/data preparation boundary; do not merge its rules into settlement logic.
4. In approved **private** runtime, load authorized Clean Branch Master. Test official/alias/SOL matches, original branch, invoice-generated location, service month, tax numbers, exact invoice unique ID, and each original invoice total; reject unresolved cases.
5. Isolated AWS staging: operator inventories current last-working Docker image digests, running containers, Caddy routes, backup/rollback, and Firebase auth. Build a new immutable candidate without changing production traffic, mounted volumes or finance data.
6. Run exact-header, source financial value parity, auth/session isolation, zero-write, backup/restore and rollback QA. Never use a synthetic PASS as evidence of production financial parity.
7. Request explicit owner approval before any application activation, financial permissions, production database connection, settlement or deployment cutover.

## Manual-correction rule
Treat every missing/contradictory source as REVIEW_REQUIRED; log evidence and correction. No automatic guessing, silent SOL rewrite, invoice recreation or credit-note conflict resolution.

## Known blocker
**WORKSPACE_DEPLOYMENT = NOT_PERFORMED**. Source QA is prepared but not yet independently executed; canonical engine and private master absent from this PR. These are release gates, not an instruction to bypass them.
