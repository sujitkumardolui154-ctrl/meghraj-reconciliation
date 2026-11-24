# SBI R28 — Owner Deployment Policy: No Separate Finance Certification For Calculation/Reports

**Decision recorded: 24 November 2026 IST**  
**Scope: calculation and reporting application deployment, WITHOUT financial posting.**

## Owner directive / decision

The owner has expressly requested that the SBI Reconciliation application be deployable without a separate **financial certification process**, and that individual invoices, payments or matching proposals which fail the approved reconciliation rules be **eliminated from calculation only**, without imposing a blanket block on unrelated eligible records.

This replaces *financial certification as a precondition for calculation/report deployment*. It does **not** declare invalid payments to be valid or grant authority for financial settlement, database writes, payment-status `OK`, bypass of source authentication or creation of a fake Finance approval.

## R28 implementation in development branch

The independent `scripts/ci/sbi_r28_owner_deployment_and_row_exclusion_policy.py` provides two pure, explicit boundaries:

1. **Deployment scope policy:** `CALCULATION_AND_REPORT_NO_FINANCIAL_WRITE` does **not require a separate formal Finance certificate**. A controlled deployment candidate can be evaluated from operator-reported fresh source, test pass, effective role/access checks, immutable source/audit and disabled financial writes. These self-reported checks are NOT certified by this module. No AWS deployment is performed.
2. **Row-level calculation candidate partition:** each previously screened source row is `PASS`, `EXCLUDE`, or `HOLD` with explicit reason codes. Duplicated invoice numbers or bank event identifiers are individually excluded as a group. An excluded source or proposal cannot enter a calculated candidate pair; other independent `PASS` rows continue. Original source rows are never deleted. Candidate pairs are **not** financial allocations and no `PAYMNENT!M` status is written.

This is a **scope separation**, not the full v2.51/v2.39 rule parser/allocator and not the actual AWS operational deployer. No real UTR proof, source file data, Excel financial writer, Firebase token or production database enters GitHub or CI.

## What does and does not block

| Check | Calculation/report deployment | Actual settlement/database write |
|---|---|---|
| Formal, independent Finance-certification certificate | **Not required** | Remains separate, not granted here |
| Failed invoice/payment rule, unrelated to other records | Exclude/HOLD only affected row or proposal; continue other candidates | Never post affected record |
| Duplicate invoice or bank identity | Exclude affected identity group | No duplicate settlement |
| Bad/missing source, broken auth or failed code/runtime tests | Technical deploy not ready | Forbidden |
| Approved Master/Matrix matching implementation | Required for claiming real matching, not supplied by this policy helper | Required, and finance scope still locked |
| Client/bank UTR verification | Evidence needed to confirm settlement, not a certificate to deploy code | Must not claim verified without actual proof |
| AWS host release access | Must be actually demonstrated by the host/operator | Must not be inferred from GitHub CI |

## Acceptance and next engineering work

- Developer candidate screening and tests may merge into **development** without a formal Finance sign-off.
- To run actual calculation on user-uploaded XLSX, connect the **complete** Master v2.51/Matrix v2.39 implementation, genuine current-run FFI-001 source, verified SOL master, payment evidence, independent row-level method QA and v2.18 output writer. The previously developed Case 2.6 method coverage is synthetic contract QA, not a complete runnable production engine.
- Live application deployment requires a working authenticated runtime, effective least privilege, tested before/after release and rollback, and the owner's authorized operational access. No Finance certificate is required for the calculation/report scope. Do not alter or bypass the existing read-only/report AWS gates or financial-write endpoint locks.
- To enable genuine financial postings a **separate** explicit owner instruction and safe financial write integration are needed. No such implementation/authorization exists in R28.
- The earlier historical user file can serve as an explicitly supplied fresh input to a *separate* runtime only where FFI-001 current-run provenance is actually captured; never silently use Drive historical data.

## QA

30 new synthetic negative/positive regression tests cover no-certificate deployment scope, technical readiness refusals, individual invoice/payment exclusions, duplicate identities, DNM provisional holds, match source preservation and no actual financial mutations. Existing 1,086 synthetic/disposable tests should run in the combined CI; **1,116 expected**, subject to exact-head GitHub Actions verification.

## Current operational claim

`formal_financial_certification_required_for_calculation_deployment=False`  
`production_financial_write_enabled=False`  
`financial_apply=LOCKED`  
`actual_aws_deployment_performed=False`  
`source_bank_rows_reconciled_by_this_module=0`

This owner policy is about **not unnecessarily delaying software deployment**; it is not an assurance that real bank ledger transactions are settled.
