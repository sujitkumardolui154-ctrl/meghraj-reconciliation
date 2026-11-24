# 2026-11-25 — Resume: Invoice + GST private staging integration

**Workstream:** SBI Reconciliation Workspace / Meghraj Express invoice generation
**PR:** #182 (draft; not merged into live)
**Owner approval:** Corrected six-page MXP18430 PDF design APPROVED on 2026-11-24.
**Scope:** SOURCE REVIEW and ISOLATED QA ONLY. No AWS financial release.

## Data source inventory (read only)

1. Authorized connected Drive: `SBI_SOL_Branch_Master_FINAL.xlsx`,
   the exact raw workbook SHA pinned in `NEXT_MILESTONE_PRIVATE_STAGING_20261124.md`.
   It is **not** included in the GitHub tree (public rule files are).
2. Its review summary declares 1,484 canonical records, followed by 19
   supplementary review entries. The workbook explicitly declares
   `WORKING REVIEW — NOT FINAL` despite its filename.
3. Source billing location is not necessarily the invoice-issuing location,
   and private recipient title/location evidence is missing for many rows.
   Never infer verified invoice addresses from a human/routing label.
4. Legacy `sbi invoice format FEBRUARY 2026.xls` exists in connected Drive;
   native Excel layout parity is separately pending. User approved the
   corrected six-page PDF as the current reference, not a migration of
   historical MXP18430.
5. The approved private vendor ZIP has passed local SHA256 checks:
   archive, inner logo and profile manifest. Private data stays outside GitHub.

## Additional safety gates implemented during resumed milestone

- `003_verified_sol_uniqueness.sql`: partial UNIQUE index on verified SOL.
  Prevents concurrent branch imports assigning the same SOL to two verified
  customers; rejects source conflicts rather than guessing.
- `load_private_branch_master.py`: prohibits two approved input identities
  claiming one SOL, and prohibits an existing row or SOL silently changing
  name, address, generation location, recipient title, GST classification
  or GSTIN. Verified-subset mode still requires per-row private evidence.
- `private_vendor_loader.py`: previously used UPDATE on conflict.
  Now a repeated import is **idempotent only if every approved original
  logo/legal/bank/header field matches**. Any difference requires separate
  owner review; no silent legal/bank/detail override.
- Synthetic isolated PostgreSQL regression covers duplicate SOL index,
  source collision, existing address conflict, and private vendor conflict.
- No data from the master, bank instruction, GST private profile or customer
  address has been committed into GitHub.

## AWS operator sequence (NOT executed here)

1. On a trusted isolated operator machine, download the verified raw
   source master and approved private vendor ZIP from their authorized
   storage. Verify their pinned SHA256 digests before doing anything.
2. Snapshot the dedicated PostgreSQL `invoice_qa` database and prove restore.
   Confirm `SELECT current_database()` equals `invoice_qa`. Never run
   this against the financial production DB.
3. Apply additive SQL migrations **001, 002, 003 in order** on the isolated
   QA DB; if 003 reports duplicate SOL, stop for review.
4. Use `master_workbook_gate.py` to export only canonical candidates to a
   private mode-0600 CSV. Obtain separately approved row-level recipient
   names/addresses, branch generation locations, class/GSTIN and reviewer.
5. Run the reviewed-subset private import against `invoice_qa` only.
   Review exclusions separately and do not promote all 1,484 automatically.
6. Run `private_vendor_loader.py` using the approved private ZIP, then
   `sbi_invoice_gst_aws_staging_readiness.py --qa-db`. Confirm original
   logo and legal profile in the isolated DB by SHA, without printing secrets.
7. Run signed-in staging-only tests for branch dropdown, preview (zero
   writes), invoice PDF layout, invoice registry atomic insert, duplicate
   rejection, verified GST XLSX headers and all financial write locks.
8. Keep finalize flags disabled in the public/live AWS service until
   independent authentication, backup/rollback, source parity and explicit
   production release authorization are confirmed.

## Current release criteria

| Gate | Status |
|---|---|
| Approved invoice printable reference | APPROVED |
| GitHub SOL matcher integration | CODE PRESENT |
| Actual Drive source located | CONFIRMED |
| Source review declaration | WORKING REVIEW — NOT FINAL |
| Private asset archive hash | VALIDATED LOCALLY |
| Duplicate SOL and source-snapshot protections | IMPLEMENTED FOR QA |
| Automatic whole-master approval | PROHIBITED |
| Real isolated AWS DB source/profile import | NOT EXECUTED |
| Authenticated AWS E2E | NOT VERIFIED |
| Production deployment/financial reconciliation writes | NOT PERFORMED |

This file is a development receipt, **not** production approval or evidence
that a live AWS instance was changed.
