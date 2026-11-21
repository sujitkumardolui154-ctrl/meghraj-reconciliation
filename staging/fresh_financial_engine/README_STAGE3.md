# NEW engine 21 11 2026 — Stage 3 Mock Integration

**Scope:** Python-only isolated integration between existing D-030 fabricated 3-column evidence, D-031 mock receipt approval and the fresh v2.51 in-memory allocation **proposal** engine. **No live AWS route or financial writer is enabled.**

## What is actually implemented

- Exact source upload columns remain `Description | SOL ID | Credit Amount`. The original `PAYMNENT!I` bank credit claim is independently cross-checked **only in fabricated D-030 sidecar examples**.
- D-030 validates per-row digest, fake bank date/UTR and mock post-activation cutoff. D-031 atomically registers fake receipt and fake UTR under uploader-only role, then a different fake reviewer confirms the receipt.
- `Stage3MockBridge` binds an immutable deep copy of reviewed source rows and signed-by-*no-one* fake sidecars; only fake contexts in the test harness supply client identity, SBISA flag and explicit invoice refs. No three-column spreadsheet provides these fields by itself.
- The existing `sbi_engine.evaluate()` calculates **proposals only**, using same-SOL, TDS, service-period, date and protected invoice controls.
- A separate SQLite `:memory:` mock candidate ledger under a thread lock atomically tracks receipt decisions and per-invoice proposed capacity. Duplicate mock receipt proposals are idempotent; competing batches above invoice capacity are held and rolled back. Real database/ledger/settlement writes are impossible from this module.
- Any engine hold blocks **all** mock ledger updates for that batch. No partial failures silently produce new reservations.

## How to run locally

Run from Git checkout root:

```bash
PYTHONPATH=staging/fresh_financial_engine:staging/aws_login_v150 \
  python -m unittest discover -s staging/fresh_financial_engine/tests \
  -p 'test_stage3_mock_bridge.py' -v
```

Existing synthetic-only AWS server and its 127.0.0.1:18087 container are **unchanged**. Stage 3 is an offline source-level development/QA path. No new HTTP POST routes are added.

## Unresolved release blockers

- Actual authenticated Firebase principal and SBI bank source authority, trusted UTR and bank date (fake mock roles are not authentication).
- Server-controlled real activation cutoff and verified **new-only** invoice source; historical records may be used for reference analysis only, never replayed or modified.
- Production transactionally durable new-only database with read/write roles, backups and idempotency under multiple workers/hosts (SQLite `:memory:` is NOT durable).
- Repaired v2.18 writer; complete GST-later/base-only/cross-SOL approved methods; separate explicit owner finance release instruction.
- One consolidated real integration/security/rollback QA on the exact deployable source, without repeating passing unchanged isolated tests.

**RELEASE_STATUS=MOCK_STAGE3_ONLY, FINANCIAL_APPLY=LOCKED, HISTORICAL_FINANCIAL_DATA=NOT_PROCESSED.**

## Isolated AWS Stage 3 preview (source PR #134)

The Stage 3 branch extends the **isolated** synthetic Docker image with only a fixed-input `GET /api/stage3/synthetic-bridge` read-only probe, and includes the pre-existing D-030/D-031 modules in that image. The probe creates and destroys mock `:memory:` ledgers entirely inside one request. No caller-supplied payment, UTR, bank date or customer data is accepted. POST/PUT/PATCH/DELETE remain denied HTTP 403.

The current deployed Stage 2 AWS container is not modified by pushing this source. An operator must separately run the SHA-pinned staging script against the Stage 3 branch; that replaces **only** the standalone synthetic staging container listening on `127.0.0.1:18087`. If staging validation fails, redeploy the prior Stage 2 pinned worktree. The existing public dashboard, reporting and Caddy routing are not changed.