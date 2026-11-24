# SBI R26.9 — Case 2.3 Master v2.51 ⇄ Matrix v2.39 read-only integration

**Owner direction:** Connect the existing Matrix candidate engine to the Case 2.2 Owner Option B *one-fresh-workbook* Master ledger in controlled development. Do NOT infer approval from historical source, TDS guess or a self-asserted proof. `FINANCIAL_APPLY=LOCKED`; production main is unchanged.

## Sources and scope
- Read directly from the approved 28 October v2.51 repair blueprint: immutable source/SOL proof -> exact reference + date/service/TDS -> documented GST and SBISA/parent-child -> DNM-01 provisional -> global unique allocation adjudication -> waterfall LAST -> final GST/duplicate decision -> v2.18 writer -> independent QA -> separate Finance release.
- Development code `scripts/ci/sbi_r267_readonly_real_candidate_engine.py` already supplies *review candidates* with 0/1/2/3% HALF_UP amount hypotheses; `scripts/ci/sbi_r269_core_cash_ledger_dry_run.py` owns conservative cash-capacity reservations; `scripts/ci/sbi_r269_case22_independent_fresh_workbook.py` enforces one-upload-scoped input, hash-bound plan and no previous financial carry-forward.
- This stage connects those real-shape Python APIs, using synthetic data in public GitHub CI. No SBI customer data/master contents are committed.

## New integrated development module
File: `scripts/ci/sbi_r269_case23_master_matrix_adjudicator.py`.

1. Require `FreshWorkbook` with `upload_id`, source/master SHA, and same-upload `ScopedInvoice`/`ScopedBank`. Match every Matrix `InvoiceInput` source row, exact invoice identifier, gross and protected original S marker; match every Matrix `BankInput` source row, credit and protected original K marker. Refuse mixed/missing/duplicate populations and any identity/amount discrepancy.
2. Require exact SHA of **normalized row-level Matrix evidence**, including invoice dates/periods, bank narration, selected SOL/client pairs and supplied relationship assertions. Recheck against input after the computation. Note: these are *caller-bound evidence manifests*, not independent certification of the original XLSX bytes, bank event or authorization.
3. Call the existing R267 `plan_review_only` and **reject any candidate-engine self-claim of `OK`, financial Apply, full certification or database writes**.
4. Map qualified proposed methods to Master `EXACT_MXP_REVIEW`, `GST_COMPONENT_REVIEW`, `PARTIAL_REVIEW`, `SBISA_REVIEW` or `CROSS_SOL_REVIEW`. For cross-SOL also require both SOL/customer pairs explicitly present in selected official master. A confirmed field on a `RelationshipProof` is a synthetic documentary QA fixture, not a signed Finance acceptance.
5. Sort accepted proposals deterministically by named method priority **for review only**, then source row and invoice key. The current exact-reference planner still drives available candidates; standalone same-SOL-without-MXP discovery is **not fully integrated** here and is explicitly pending.
6. For a later bank payment held as `INVOICE_CASH_CAPACITY_CONFLICT`, mark the **entire competing invoice group** for review. Do not silently allow the first source row to win. Do not reserve its earlier proposal. Contradictory MXP references, missing service evidence, unverified SOL, GST without documentary proof and compound cross-SOL/GST remain held.
7. DNM-01 from the planner remains **provisional and unreserved** even when the amount is nearest. Waterfall is not auto-applied; the Master receives one `GlobalAdjudicationBoundary()` marker *after* earlier review candidates. No later method can reserve before global adjudication.
8. Delegate cash reservations ONLY to the existing Case 2.2 upload-isolated Master ledger. Return workbook-tagged review edges, bank remaining cash, invoice **cash coverage gap (not verified receivable)**, separate held bank rows and quarantined invoice rows. Do not assign any actual payment status or post financial writes.

## Known limits and next approved case
- No completed standalone same-SOL, multi-invoice payment distribution, final DNM-01 winner adjudication, waterfall allocation, real GST/TDS/credit-note accounting or duplicate-payment final decision. These are still missing pieces of the **complete** v2.51/v2.39 matching rules.
- No bank UTR uniqueness proof; re-uploaded identical transactions across different independent workbooks remain blocked for later production Apply review.
- Original v2.18 full-size money writer, 53-column value parity and staging financial database apply are not in this PR.
- **Case 2.4** must define exact final-status rules and resolve whether a qualifying cash/TDS candidate can ever become `OK` without independent withholding/ledger evidence; default is `SUSPENSE` until all approved conditions and independent QA pass.
- **Case 2.5–2.6** will need per-edge forensic evidence, separate accounting reference oracle, signed same-upload simulation and all method coverage.

## QA acceptance and status
66 synthetic adversarial tests cover source hash and row binding, method ordering, partial/GST/SBISA/cross-SOL, contested invoice groups, DNM holding, fraudulent Matrix status/amounts, old-history isolation and source protection. The combined CI repeats the previous 865 tests plus 66 new; the GitHub workflow result must actually pass. Scope passes are NOT production certification.

**`R269_CASE23_DEVELOPMENT_SCOPED_ONLY`; `FINANCIAL_APPLY=LOCKED`; `REAL_DB_WRITES=0`; full Master v2.51 / Matrix v2.39 NOT certified.**
