# Stage 4 Release Gate — outstanding work

| Requirement | Stage 4.0 | Blocking for real finance |
|---|---|---|
| Exact three-column upload shape | Signed digest contract implemented | Must bind to existing authenticated upload route |
| New-only bank cutoff and UTR | Strict offline validator implemented | Bank-issued evidence authority not connected |
| Signed source metadata | HMAC/internal gateway proof implemented | Actual bank and invoice source verification pending |
| Distinct uploader/reviewer | Offline Principal roles implemented | Real Firebase role/session binding pending |
| Durable ledger | Separate SQLite candidate store tested | Production storage, backups, privileged roles pending |
| Over-allocation/replay | Invoice/payment capacity, idempotency and WAL tests | Canonical rule/multiphase ledger audit pending |
| Full v2.51 matching | Stage 3 synthetic proposals only | GST later/base only/cross SOL/complete precedence pending |
| v2.18 workbook writer | Quarantined old source not used | Repaired source-preserving writer pending |
| AWS isolation | Stage 3 confirmed healthy by user screenshot | Stage 4 not deployed |
| Finance Apply | Explicitly disabled | Owner final approval + QA required |

**Decision: STAGE4_SOURCE_FOUNDATION_READY; FINANCIAL_PRODUCTION_BLOCKED.**