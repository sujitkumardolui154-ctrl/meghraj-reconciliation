# SBI manual 35→53 source/report financial parity — sanitized evidence (2026-11-06)

**Private offline audit; financial data and invoice identifiers are NOT uploaded to this public repository.**

## Frozen inputs

- User-provided original `Invoice Details.` workbook: **14,374 original invoice rows, 35 approved columns**; workbook SHA-256 `cae074720d0098ac9f9e3847e3e8edfa4b49cbba21ea755efb5833c91019f665`.
- User-provided `sbi-ok-v1.4.2.csv`: **10,560 exported report rows, 53 approved columns**; SHA-256 `2a85c1873a61ea38441bb2516536c84b147d3f13f3d0016d179a5a22d6f57fe3`.
- Original workbook has `PAYMNENT` (14,898 data rows) and `Credit Note` (1,072 data rows, **24 columns**), but this is not itself an approved 18-column Credit Note report.
- `sbi-unpaid-v1.4.2 (1).csv` has 53 headers but zero data rows.
- Approved 35→53 positional mapping: 35 columns map to 53 with model columns omitted; preserves both original `Branch Code` positions. All approved locked header positions matched exactly.

## Verified limited scope — 53-column report is a source subset

- **10,560/10,560 OK-report rows each mapped to a distinct original workbook row** using invoice reference, source identity fields and monetary values. Source row IDs are unique across matched records.
- **10,548** invoice keys were unique, **6** report rows required disambiguation of genuine duplicate invoice references by other matching fields, and **6** placeholder-reference rows were matched by independent identity/amount fields. Those 12 invoice identities remain flagged for review.
- On the 10,560 mapped rows, all **35 original source fields** match the approved 53-column projection after **reversible formatting normalization** (Excel serial dates ↔ ISO timestamps, floating-point display precision ≤₹0.01 for numeric values, safe leading-apostrophe CSV escapes and 0↔00:00:00 for date/time fields). **Zero mapped-field value differences.** This is source-to-export data preservation, NOT bank payment reconciliation.
- The original master has **3,806 nonplaceholder invoice keys not present** in the OK subset; other report categories have not been fully verified.
- Financial worksheet formula cached values were compared; source formulas were **not independently recalculated**.

## Data-quality exceptions that remain unchanged (Error Report Issue #76)

- Original workbook: **4** gross arithmetic discrepancies >₹0.01; **2** appear unchanged in the OK export. Original has **2** gross/tax nonnumeric-or-blank rows; OK report **1**.
- Original source: **8** genuine duplicate-invoice groups; OK subset **1** genuine duplicate group. There are **6** placeholder invoice references in both original and exported subset, mapped by other fields but not valid invoice keys.
- Report source fields: **4** disagreements between the two source Branch Code positions, **13** mismatches of source branch and Model SOL, **20** blank Model SOL IDs.
- All 10,560 exported rows have positive source payment values and status `SKIPPED — EXISTING PAYMENT`; that means no new independent reconciliation proof.
- Report contains **4 financial amount cells serialized as ISO dates** (3 in total-payment field, 1 in credit-note amount field). Their Excel date serial values agree with the original source; type/display still requires review.
- Source bank ledger contains **11,841** numeric credit entries. Narration-only screening found **757** entries with MXP-like references and **697** distinct OK-report invoice references appearing in bank text: these are candidate textual references only, **not bank allocation proofs**.

## Independent gates remain blocked

1. Bank-to-invoice allocation, month/SOL/TDS rules and original payment evidence **NOT VERIFIED**. Never infer PAID/OK from positive source cells or narration candidates.
2. Full 53-column master coverage across Unpaid/OK/Balance Review/Suspense **NOT VERIFIED**. The provided OK report is not the entire master.
3. Approved 18-column Credit Note report parity/conflict resolution **NOT VERIFIED**.
4. Immutable backup manifest, cryptographic integrity and isolated restore/rollback **NOT VERIFIED**.
5. Real Firebase acceptance, release approval and production cutover **BLOCKED**.

**Result:** `MAPPED_SOURCE_TO_OK_EXPORT_VALUE_PARITY=PASS_10560_OF_10560`; `BANK_RECONCILIATION_PARITY=NOT_VERIFIED`; `FINANCIAL_RELEASE=BLOCKED`; `ORIGINAL_FILES_MODIFIED=NO`; `FINANCIAL_DATABASE_WRITES=0`.

Do not disclose raw workbook/report rows in GitHub; private row mapping and exception exports remain only in the owner's ChatGPT attachments. The attached data are user supplied; no independent deployed-database snapshot equivalence was asserted.
