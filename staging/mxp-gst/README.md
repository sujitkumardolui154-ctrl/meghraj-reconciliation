# MXP GST branch-matching rules — v2.7 (staging only)

This folder packages the user-approved MXP GST naming rules for review in the SBI Reconciliation Workspace. **It is not a financial reconciliation engine or a production deployment.**

## Scope and separation
- Read-only branch/alias resolution; no settlement, invoice-status changes, database writes, or financial calculations.
- Do not import historical invoice transactions or private customer/branch master workbooks into this public GitHub repository.
- Load the authorized `Clean Branch Master` separately in the private runtime; it is **not** shipped here.
- Reject ambiguous/incomplete names rather than guessing a SOL. Keep source text intact for the GST final output.

## Mandatory GST output contract
A FY; B Invoice Branch; C Invoice Generate Location; D Month; E Invoice Date; F Branch Code; G Client Name; H Branch Code; I GST NO; J Invoice No; K Taxable Amount; L CGST; M SGST; N Total Bill Amount; O Error / Verification Flags; P Original Extracted Branch Name.

- `Client Name` is the unique verified `Official Branch Name`, or the verified non-SBI customer name. Never place `SBI`, `REVIEW`, `MISSING`, or other flags in this field.
- Columns F and H must match; five-character SOL IDs are stored as text.
- Column P is the unmodified original branch-name string; Column O contains all missing/conflict/verification flags.
- Month matches the source's displayed service-period text, not invoice-date month by default.
- Invoice Branch prefers invoice-specific evidence; historical SOL matches must carry evidence and must not silently become verified.
- Invoice Generate Location is taken from an unambiguous source filename, otherwise blank.
- Source numbers must be independently reverified after assembling the GST output; total bill = taxable + CGST + SGST, reconciled against source gross.
- GSTIN classification: verified SBI banking client `19AAACS8577K3ZK`; verified SBI FUND `19AAACS7339D1ZB`; others/unverified blank.
- Specific owner-approved mapping: SBI FUND MANAGEMENT LTD — KRISHNANAGAR → SOL `99922`. Do not apply this SOL to other locations.
- On initial `MXP GST GPT PROMPT`, ask for fresh source files and invoice ranges only. Previous transactions are not reusable sources.

## Alias policy
Use a **single** `Search Aliases` column in the private master, preserving `Official Branch Name` and SOL. Remove `Column1`, duplicate alias columns, and `Billing Location Frequency Evidence` from the cleaned schema. Old aliases must be reviewed and may only be promoted when their official identity is unique and evidenced.

CAC/cac means `CASH ADMINSTRATION CELL` (also accept correctly spelled `CASH ADMINISTRATION CELL`) only when a location follows it. CAC MALDA → `CASH ADMINSTRATION CELL MALDA` / SOL `18583`. Bare CAC must be held. `CURRENCY ADMN CELL BURDWAN` is not synonymous with CAC BURDWAN without independent approval.

### Rejected alias assignments (v2.7)
| Official entry | SOL | Disallowed alias |
| --- | --- | --- |
| LHO(cramc) | 03970 | Office Administration Departement (LHO) |
| RBO 4 BIDHANNAGAR | 14871 | RBO 3 BIDHANNAGAR |
| RBO 5 KRISHNAGAR | 14872 | RBO 6 KALYANI |
| RBO 4 DURGAPUR | 14877 | R.B.O. |
| RBO 3 SILIGURI | 62948 | RBO-III |
| RBO 2 SILIGURI | 14879 | RBO 3 SILIGURI |

Additional verified identity: RBO 6 KALYANI has owner-approved SOL `18252`. RBO-III without a location and generic RBO/R.B.O. cannot auto-resolve.

## Release gate
This is a **review branch only**. Keep the master review exceptions and financial production freeze. Independent synthetic QA, source verification, conflict review and owner release approval are required before any application deployment.
