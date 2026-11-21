# NEW engine 21 11 2026 — Stage 4.3 newer-source integration

**Status:** synthetic-only source-readiness adapter; 22 Nov 2026. No production permission.

## Scope and source basis

The previous Stage 4.2 end-to-end test used the approved *nine-tab legacy v2.18 output* layout (Invoice No at J, gross at N, output model AI:AM). An existing read-only `sbi_engine/reference_schema.py` recovers the separate newer original SBI source header profile, with exact **two** input tabs:

- `PAYMNENT` A:L: C bank transaction date, E narration, F text SOL, I credit, H debit (never the incoming payment).
- `Invoice Details.` A:AI (35 columns): E service month, F invoice date, G text SOL, H client, **K invoice number**, L taxable, M CGST, N SGST, **O gross**, **S original paid marker**.

The newer original **AI** overlaps the legacy writer model start **AI:AM**. The two layouts are intentionally **not interchangeable**. This module does not silently remap original source cells, change invoice numbers, or invoke the v2.18 writer.

## Implemented source adapter

- `new_only_adapter.py` reads only explicitly fabricated `SYNTHETIC_*.xlsx`, at most 2 MB/100 source records, using read-only, bounded OOXML XML inspection. It validates the two exact sheet names and row-one headers via the recovered header-only reference profile. No historical workbook is opened.
- It verifies the exact source file's SHA-256 against both Stage 4 internal-gateway HMAC-signed `SBI_BANK_EVIDENCE_V1` and `SBI_INVOICE_EVIDENCE_V1` envelopes. The exact existing `Description | SOL ID | Credit Amount` upload row is separately bound to the signed credit and original `PAYMNENT!I` source. **HMAC authenticates the internal signer only, not SBI bank origin.**
- All relevant original text and numeric coordinates must match signed evidence; malformed dates, formula-derived financial inputs, blank/incorrect amounts, numeric/stripped SOL IDs, duplicate source rows, bad signatures, invoice/client/SOL/period conflicts and any nonblank original S marker (including numeric zero) fail closed. No fuzzy matching or invented SOL master approval.
- It verifies separate fabricated intake and reviewer identities against Stage 4's role contract, creates one *temporary* SQLite WAL candidate ledger receipt and invoice, records a separate review, requires **zero reservations**, and deletes the database after review. No production DB, Firebase route, bank API, settlement status, real finance writer or AWS deployment.
- `snapshot_contract` is a pure source-coordinate validation entrypoint for independently supplied snapshots; `review_new_only_pair` is the full fabricated source + HMAC + dual-review integration.

## Tests and limits

Test files: `tests/test_source_contract.py` (20 pure source/logic cases) and `tests/test_workbook_e2e.py` (13 fabricated Excel + signed review cases). Local full-runtime tests: **33/33 pass**, no actual records. A separate one-pass GitHub gate also runs the unchanged Stage 4, 4.1 and 4.2 source QA. The GitHub runner may lack `artifact_tool`: full workbook tests are skipped with explicit `NOT_RUN` reporting unless the runtime is available. Local workbook coverage is not a substitute for independent finance certification.

Legacy v2.18 export remains **BLOCKED_SOURCE_COLUMN_OVERLAP** for these new-source files. The adapter accepts one fabricated source payment/invoice pair to avoid making claims about unverified multiple-row or many-to-many matching. It accepts ISO text dates and one `YYYY-MM` service period only; actual Excel numeric dates and service-period ranges require a separately approved schema/normalization rule. Source authority, official SOL master proof, production Firebase/CSRF authorization, real TDS/GST/SBISA/waterfall matching, durable finance writer, independent full workbook QA and owner release are still missing.

**No actual bank/invoice data read, no existing AWS service changed, no financial Apply, zero money postings.**
