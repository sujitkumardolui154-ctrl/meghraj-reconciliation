# SBI Reconciliation — One-Gate Fast-Track Production Recovery
2026-11-21 | Owner-directed minimum testing, strictly **new-only** financial processing

## Status verified
- AWS runtime code identity last verified by owner: `ce3100b176151b6d5446a88be3241971b5ef51f7`. `sbi-source-reports-v1-stage` is running, Payment Evidence upload blueprint/UI registered, and Caddy proxies `/dashboard` and `/api/*` to Source Reports v1.
- Existing fixed payment upload headers **must stay** `Description | SOL ID | Credit Amount`.
- Existing `/api/payment-reconciliation/status` and `/preflight` check evidence/receipt integrity only; clean receipts fail closed with engine `NOT_CONNECTED` and no financial writer. Real Apply button disabled. No production finance action can be claimed.
- The archive `01-Engine-Source/FINANCIAL_ENGINE_FIX_PLAN_2026-10-28.md` describes Master v2.51 / Matrix v2.39, incomplete full-engine integration, archived Builder package fingerprint `189cd6e9cff399412a50520afd0d7520752a3682c707751ec1f853c57c7ad256` and writer candidate `85606f226ebb7b6555a648386021b3df2765d29c9f37312d499029b335b0719b`. They are historical **SHA-256 source-code fingerprints, not Git commit IDs**, not approval evidence or permission to run archived financial data. The source ZIP files have NOT been located or independently attested as a complete deployable allocator. Earlier use of git cat-file against these 64-character hashes was an invalid Git-object check.
- D-025/026 allocation candidate/waterfall and D-029/030/031 synthetic provenance work are deterministic synthetic proof-of-concept modules, not complete certified production engine or live writer. D-029 through D-031 are consolidated for review into PR #131.

## Fastest viable recovery — no artificial stage numbering
**Recover first.** Use `bash staging/aws_login_v150/fasttrack_source_recovery.sh`. It checks only the two exact original ZIP filenames in the archived Builder inbox paths, does not open or hash their content. Source fingerprints must not be passed to `git cat-file`. If canonical source is absent from the current repository, recover from the authoritative ORIGINAL code repository or source archive; do not invent a settlement module or copy unverified synthetic code into production finance routes.

**One minimal integration patch.** Once independently verified, source-pin the approved canonical logic, server-controlled new-only payment authentication / bank date / UTR provenance and separate post-activation invoice + allocation ledger in the existing authenticated Flask workspace. Do not change Caddy `/api/*`, add duplicate upload tabs, alter three-column XLSX, or include historical data mounts. Keep `PAYMNENT` A:L and old allocations unreachable. Do not treat fresh upload timestamp as proof that the bank payment was newly received.

**One consolidated mandatory QA and isolated AWS stage** — re-use previously passing exact-hash tests wherever still applicable. Only the following new/changed risks require fresh verification:
1. New-only source provenance (server cutoff, UTR, Column I, invoice eligibility / SOL / branch / period) and historical-data isolation.
2. Approved reconciliation rule precedence including 0/1/2/3% TDS Decimal HALF_UP, SBISA SOL 1, full/partial waterfall, DNM-01 negative cases, protected/credit-note holds and duplicate/over-allocation conservation. No real financial fixture.
3. Authenticated upload/approval, idempotent transactional writer **in a completely isolated new-only test ledger**, negative permission tests and read-only report parity.
4. Pinned AWS staging image, health/auth route smoke test and tested rollback preserving existing Caddy/reporting.
Any failure blocks financial release; "previous tests passed" is acceptable only when exact source/behavior is covered and no failure was left unresolved.

**Release only with explicit owner approval.** Source-only GitHub CI and an AWS-running UI are not finance release authorization. Do not flip the disabled Apply control, enable production database credentials, run a live finance write, scan historical books, backfill, re-evaluate existing suspense or change old payment statuses. Production financial button stays locked until owner approves the exact new-only writer and required QA evidence.

## Required output from the engineer
One actionable PASS/BLOCKED report containing: canonical source ID and provenance; approved rulebook version; exact new-only cutoff/auth evidence; immutable image ID; CI pass evidence; one isolated new-ledger source-to-output test; role/idempotency denial; rollback pass; owner's explicit finance-write approval. Avoid multiple QA cycles or unnecessary speculative feature development.

**FAST_TRACK=SOURCE_RECOVERY_FIRST; NUM_QA_GATES=ONE_CONSOLIDATED; HISTORICAL_DATA=FORBIDDEN; FINANCIAL_APPLY=LOCKED_UNTIL_AUTHORIZED.**

## Corrective source identification (2026-11-21)
The previously cited 64-character `189cd6e9...` and `85606f22...` values are **SHA-256 code fingerprints**, not Git commit objects. The original records were `ENGINE_BUILDER_SB18_PRE_BC_CHAIN_REMEDIATION_20261028_1939IST_REPORT_PACKET.json` and `REPORT_ARCHIVIST_Q218_SB18_INTAKE_20261028_200750IST_INDEPENDENT_STATIC_VERIFICATION.json`. They identify two source packages:
- `ENGINE_BUILDER_SB18_PRE_BC_CHAIN_REMEDIATION_20261028_1939IST.zip`, archive SHA-256 `27149c9ab65065db51c14748708d0ee6775176d66d49a555711eb889b22c1e5f`, code SHA-256 `189cd6e9cff399412a50520afd0d7520752a3682c707751ec1f853c57c7ad256` (39 entries, not a certified full allocation engine).
- `OUT_SCHEMA_V218_STAGING_BUILDER_20261028_1932IST.zip`, archive SHA-256 `b85bf68b2e241a71da4daccc3ff666f9576eb1c5a7ac7d46239d7003c9670c81`, code SHA-256 `85606f226ebb7b6555a648386021b3df2765d29c9f37312d499029b335b0719b` (17 entries, staging writer candidate).
The proposed source-package location from handoff records is `/DIL_PRIMARY_AGENT_HUB/My_sec_Payment_Reconciliation/INBOX/ENGINE_BUILDER`. Current Google Drive search and Library title search did not locate these ZIP bytes. The original packages must be located and their manifests/content verified before treating them as recoverable source. No historical financial workbook may be opened, read or used for recovery. Known Builder/Primary tests are not production financial approval.
