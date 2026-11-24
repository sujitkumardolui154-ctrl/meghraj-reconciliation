# SBI R26.9 — Case 2.2 Owner Decision B: each fresh workbook is an independent ledger

**Approved by owner:** Option B (24 Nov 2026). Each new invoice/payment workbook is reconciled **only against records in that same uploaded workbook**. Prior/archived SBI reconciliation rows, earlier payment statuses, previously allocated bank credits and prior invoice balances are never silently imported or carried forward. Fresh uploads need not have the historical number of records or historic payment K values.

## Integration boundary
- New `scripts/ci/sbi_r269_case22_independent_fresh_workbook.py` binds a `FreshWorkbook` with its **upload_id**, original/source SHA-256, selected master SHA-256, immutable scoped Invoice/Bank objects and immutable scoped Matrix proposals.
- Every invoice, bank row and Matrix edge must bear the **same upload_id**. Foreign records or proposals cause atomic refusal. The complete normalized source contents and ordered proposed plan have their own exact expected SHA256 fingerprints to detect stale/altered rows and edge allocations.
- Execute **one** fresh workbook per pure in-memory dry run. No database reads for previous allocations; any explicitly supplied previous allocations or previous bank statuses are rejected. No history imported and no cross-workbook money allocated. No global state or persistent balances.
- The existing Case 2.1 core checks all invoice/payment source row duplicates and invoice numbers **within the workbook**, all protected source S/K fields, exact Decimal bank and invoice capacity, one global adjudication boundary and waterfall-last. Provisional DNM still cannot reserve cash.
- The output includes upload-tagged `scoped_shadow_edges`, `scoped_shadow_bank_rows` and `scoped_shadow_invoice_cash_rows`, alongside immutable checksums and receipt flags. Cash coverage gap is not certified remaining receivable.

## Important Option B operational distinctions
- The same invoice identifier and original physical Excel row can appear in **different** independent uploaded workbooks during QA. Their local capacity accounting is separate. That is not permission to double-post a bank transaction in production.
- **Current-upload** original Invoice Details. S and PAYMNENT Record For Me K markers remain protected, including a numeric zero. Option B does not mean erasing valid protected flags from the currently submitted file.
- Re-uploading identical source bytes as a distinct batch is allowed for a **read-only rerun only**; cross-upload bank transaction deduplication, re-import prevention and any production Apply are a **separate** release gate. This code explicitly reports `cross_upload_transaction_duplicate_detection_completed=False`.
- Source SHA is the upstream source-reader's reference; this pure ledger does NOT itself parse or authenticate original XLSX bytes or signed bank transactions. The normalized batch digest authenticates *binding to the asserted input*, not bank provenance.
- A new-only three-column upload remains separated by R26.8; missing bank date/UTR cannot be guessed.
- No old paid status is imported from historical v2.18. No `OK` or `Duplicate Payment` outcome is certified by this cash-only component.

## QA and remaining work
- 62 fully synthetic negative/positive tests assert separate workbook accounting with colliding invoice numbers and bank keys, strict per-upload rejection, no history carry, changing source/master/plan digests, duplicate source rows within the same workbook, protection of source markers, partial/full conservation, no global state and upload-tagged outputs.
- Combined CI re-runs the previous **803** synthetic/offline/disposable PostgreSQL checks and the new 62. Neither private SBI customer financial data nor the selected October master is committed to GitHub.
- **Next Case 2.3:** Connect an approved Master v2.51 / Matrix v2.39 candidate-and-evidence interface to this per-upload core; finalize matching priority, same-upload global adjudication and cross-method conflict controls. Amount-similar candidates and self-asserted evidence IDs must not be financial authorization.
- **Case 2.4–2.6 and Cases 3–6** remain pending: independently justified `OK`/`SUSPENSE`/`Duplicate Payment`, TDS/GST/credit-note integrated accounting, final DNM/waterfall, independent oracle and complete writer.

**Development-only scope. `FINANCIAL_APPLY=LOCKED`; `real_bank_allocations=0`; `production_database_writes=0`; complete v2.51/v2.39 NOT certified.**
