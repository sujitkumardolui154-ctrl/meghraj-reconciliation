# NEW engine 21 11 2026 — Stage 3 AWS preview

Stage 3 adds `GET /api/stage3/synthetic-bridge` to the existing isolated localhost-only synthetic Docker service; it demonstrates fixed fabricated upload -> D030 fake provenance -> D031 fake dual-control review -> fresh engine proposals -> SQLite `:memory:` mock candidate ledger.

## Expected smoke after Stage 3 preview deployment

```
SBI_SYNTHETIC_HEALTH=PASS
SBI_SYNTHETIC_DEMO=PASS
SBI_STAGE3_MOCK_BRIDGE=PASS
SBI_NEW_ENGINE_STAGE=RUNNING_LOOPBACK_ONLY
SBI_NEW_ENGINE_APPLY=LOCKED
SBI_FINANCIAL_POSTING=NOT_ENABLED
```

From the AWS host only, check `curl -fsS http://127.0.0.1:18087/api/stage3/synthetic-bridge`. It must report `stage3_probe: PASS`, `mock_candidate_ledger_edges: 1`, `mock_ledger_persistent: false`, and `financial_writes: false`.

**No real bank, invoice or historical records are read. No dashboard/Caddy/Firebase routes are changed. No financial Apply is unlocked.** This does not establish a production-grade durable ledger, bank provenance, SOL master source, full approved v2.51 rule coverage, Excel writer or release authorization.