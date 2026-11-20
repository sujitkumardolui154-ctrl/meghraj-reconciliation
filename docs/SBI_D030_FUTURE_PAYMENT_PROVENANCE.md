# D-030 — Future-Only Payment Evidence Provenance Contract (Synthetic Only)
Date: 2026-11-21 | SBI Reconciliation Workspace | Workstream D

## Owner safety boundary
The owner requested progress towards unlocking Financial Reconciliation, but prohibits any processing of historical financial invoices, PAYMNENT records, credit notes, GST, allocations, or actual databases. **Do not remove the disabled Apply button.** Real reconciliation, financial writes, old-data parity checks, migration, replay, and backfill remain blocked. D-030 performs exclusively in-memory simulation with fabricated `SYNTH-*` records and no I/O.

## Compatible with the EXISTING UI
The running AWS source at `ce3100b176151b6d5446a88be3241971b5ef51f7` has an existing Payment Reconciliation → Upload New Payment Evidence screen. Its fixed workbook must remain exactly:
1. `Description` (Excel A)
2. `SOL ID` (Excel B; **text**, leading zero preservation)
3. `Credit Amount` (Excel C; amount copied from original PAYMNENT Column I)

**Do not add bank date or UTR as a fourth column.** The new *optional future* provenance model is a separate, versioned sidecar that can be considered only after a trusted source and data authorization exists.

## New D-030 source
`staging/aws_login_v150/d030_future_payment_provenance.py` has a pure, isolated `preview_future_evidence(rows, sidecar, *, mock_activation_date, mock_submission_date, synthetic_mode=True, previous_synthetic_references=())` proof of concept.

Simulated evidence is a list of dictionary rows with the exact existing 3 headers and **fabricated descriptions only**. A separate, row-ordinal-bound sidecar requires:
- `source_kind="SYNTHETIC"`, `excel_row`
- ISO `bank_date` satisfying **mock** activation date <= bank date <= **mock** submission date
- `bank_reference` in reserved `SYNTH-UTR-*` namespace
- `source_credit_column="PAYMNENT!I"` and a positive, strictly formatted `source_credit_I` matching the 3-column `Credit Amount`
- `evidence_row_sha256` binding exact description/SOL/amount (SHA-256 is a content checksum, **not a bank signature**)

Exact batch length/field sets, text SOL, finite nonzero credit, source/sidecar row consistency, global duplicate UTR within fabricated batch, duplicate three-column source rows, and conflicts with a *synthetic-only* previous reference index are validated. **Any violation holds the entire candidate batch**—no partial acceptance. Errors contain row ordinals and reason codes only, not bank data.

The response ALWAYS states that original PAYMNENT was not accessed, original bank Credit-I claims were not independently verified, mock cutoff dates are not trusted production dates, the actor was not authenticated, no receipt was persisted, and no invoice matching or financial posting occurred.

## Critical gaps before D-030 could support real new evidence
1. Obtain owner approval for separate provenance metadata without changing fixed XLSX headers, and define supported bank evidence type and signed/protected original record.
2. Enforce **server-controlled activation cutoff**, authenticated session/owner roles, UTR authenticity, independent source Column-I proof and binding to an actual newly submitted workbook digest; in-memory claims are untrusted.
3. Implement transactional global duplicate bank reference/receipt control in a new-only, private append-only store. Existing workbook SHA duplicate detection is not transaction identity detection.
4. Add approval workflow, and ensure no historical bank/invoice/credit note/GST/settlement ledger mounts, reads or writes.
5. Complete certified SBI matching/partial/full/TDS/SBISA allocator, isolated post-activation invoice source, separate financial posting authorizations, independent QA and rollback.

## D-030 QA scope
`python -m unittest discover -s tests -p 'test_d030_future_payment_provenance.py' -v`

Regression:
`python -m unittest discover -s tests -p 'test_d029_finance_unlock_requirements.py' -v`

`python -m unittest discover -s tests -p 'test_sbi_reconciliation_readiness.py' -v`

No production API, Caddy gateway, Docker staging or AWS live change occurs.

**D030_IMPLEMENTED=PURE_SYNTHETIC_REFERENCE_ONLY; EXISTING_UPLOAD_HEADER=UNCHANGED; FULL_FINANCIAL_ENGINE=NOT_CONNECTED; REAL_APPLY_BUTTON=DISABLED; HISTORICAL_RECORD_ACCESS=NOT_PERFORMED; FINANCIAL_WRITES=NOT_PERFORMED.**
