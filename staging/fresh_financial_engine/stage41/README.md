# NEW engine 21 11 2026 — Stage 4.1 v2.18 Review-only Writer

**Status:** Synthetic source code completed; local review-only QA 19/19 PASS; not a finance release.

## Exact reference
`OUT-SCHEMA-V218-001` from `OUT_SCHEMA_V218_STAGING_BUILDER_20261028_1932IST.zip` (reference header-lock manifest of 28 October 2026). The earlier `src/staging_v218_writer.py` was not copied or trusted: the earlier output-writer candidate failed independent QA for numeric/text identity issues.

## What this fixes
- Writes `PAYMNENT` model M:W (11 exact headers) and `Invoice Details.` model AI:AM (5 exact headers) using `artifact_tool`.
- Audits every source cell's semantic **type, value, formula** in `PAYMNENT` A:L and `Invoice Details.` A:AH; audits **all** original data in other tabs.
- Verifies sheet names/order, exact header positions, complete payment-row coverage, no pre-existing model contents, leading-zero SOL identity retained as *text* (for original and model fields), formula preservation, no status/remarks formula injection and no duplicate output overwrite.
- Stages **SUSPENSE-only** rows with review remarks. No `OK` or `Duplicate Payment` statuses issued before independent financial engine approval. A real decision writer must be certified separately.
- Rejects all non-`SYNTHETIC_*.xlsx` filenames, unsafe source layouts, unexpected third-party sheets and altered protected cells. Cannot post, update invoice paid markers or interact with a database.
- Publishes output only after post-export audit succeeds; uses exclusive hard-link publication (refuses overwrite).

## What this does not do
It does not authenticate SBI bank evidence, generate candidate matching conclusions, verify real existing settlements, solve all historical header/version variants, process real payment rows, approve invoice status `OK`, or interface with AWS. The newer input workbook may have a different invoice header layout; that requires a **separate verified source-layout adapter** and is intentionally held rather than silently rewritten. The v2.18 manifest has 9 source sheet names in a fixed order; the writer does not invent missing tabs.

## Run the independent synthetic test set

```
PYTHONPATH=. python -m unittest discover -s tests -p 'test_*.py' -q
```

Requirements: Python 3.11+ and `artifact_tool` runtime. It must be run in an environment with `artifact_tool` available. The GitHub-hosted runner may not have this library; do **not** claim GitHub performed the 19 workbook tests unless its CI actually executes them. Developer QA used the available `artifact_tool` runtime locally.

## Synthetic demonstration only

Use `tests/test_v218_writer.py`'s `source(...)` and `models()` functions to make a fabricated test workbook, then `write_synthetic_v218_review(...)`. Neither the demo source nor output resembles an actual bank account or customer record.

## Release blocker
The pending production release still needs authenticated future-only bank and invoice sources, real approved v2.51 allocation precedence, an authorized write path, protected durable finance ledger, verified invoice-header mapping, a production-grade writer tested on independent synthetic edge cases, one combined security/rollback QA and **explicit financial posting authorization**. Stage 3 AWS localhost container remains unchanged and Apply stays locked.