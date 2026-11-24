# SBI R26.7 — Real-schema candidate engine and v2.18 writer verification (24 Nov 2026)

## Owner goal
Complete reconstruction and independent certification toward full Master v2.51 / Matrix v2.39 and actual v2.18 financial Excel output. This review PR delivers intermediate **development-only code**, not the required Finance-certified full engine.

## Direct source evidence examined (private runtime only)
- Original user source, cleaned source and Oct27 owner-selected SOL master have SHA-256 verified copies. Original source has 14,007 invoice rows and 14,898 payment rows; the cleaned copy has 13,873 and 14,883 respectively. The private R26.6 evidence finds nine distinct invoices with financial-source exceptions.
- Excluded 149 records remain review-only; those 134 excluded invoice rows include negative/credit-note-like values. Removing them increases apparent gross and cannot be treated as financial-neutral.
- Original invoice J/K/L/M/N are invoice number/taxable/CGST/SGST/gross; bank column I alone is Credit. Invoice S nonblank including numeric zero blocks new allocation; bank K original status must be preserved.
- Historical v2.18 workbook is a SCHEMA reference, not a same-source independent certified monetary oracle. Different invoice population and bank original K values bar copying its old OK statuses.
- No private bank line, invoice identifier, narrative, amount or master table is uploaded into GitHub CI.

## Development source and tests
- `scripts/ci/sbi_r267_readonly_real_source_adapter.py` accepts read-only original XLSX and selected Clean Branch Master bytes with exact SHA-256, parses bank C/E/F/G/I/K and invoice E/F/G/H/J/K/L/M/N/S, understands Excel serial dates, months and text multi-month ranges; quarantines missing/invalid money, numeric-format SOL and unverified periods.
- `scripts/ci/sbi_r267_readonly_real_candidate_engine.py` is a **real-source-capable in-memory candidate planner**: exact MXP and 0/1/2/3% TDS hypotheses, multi-month, protected source S/K, same-SOL official client, documentary SBISA/cross-SOL/GST, partial candidate proofs, DNM-01 (nearest <=₹1, runner-up >=₹2, <=180d), conservative cash-capacity and waterfall LAST review. It returns NO true bank payment statuses or durable ledger writes.
- `scripts/ci/sbi_r267_artifact_v218_review_writer.py` uses `artifact_tool` to attach only model M:W payment and AI:AM invoice columns to a source-copy preview, M always SUSPENSE; every candidate explicitly unapproved. Source/plan hash match enforced. No original source edit or historical OK copying.
- **60+32+30=122** new adversarial synthetic tests, combined with 535 prior tests => 657 scoped test cases on CI. CI has NO actual bank workbook or October master contents.

## Private artifact_tool physical workbook smoke
A small synthetic v2.18-compatible workbook was created, imported, modified in only permitted model columns, exported and read back using stdlib XML comparison. **0 protected original-cell changes**, original financial formula text retained and workbook sheet order unchanged. This is a legitimate small-fixture serialization result, NOT a full-workbook financial writer certificate.

## Full-size writer blocker, explicitly attempted
The 4.4MB user original source includes approximately 125k invoice formula cells. A bounded artifact_tool FULL original workbook import was explicitly attempted, but **did not complete within the bounded test**. No real v2.18 output was exported; do not claim full-size writer parity. No original workbook was modified.

## Not certified / must be resolved
1. Actual full Master v2.51 / Matrix v2.39 integrated executable parity still incomplete: global confirmed accounting ledger/partial across all methods, duplicate final decisions, credit-note tax apportionment, GST-later, verified DNM and waterfall persistence all require owner/Independent QA signed rule coverage and same-source reproducibility.
2. Selected Oct27 SOL master has 10 missing/invalid SOL identities, three zero-equivalence collision groups and unapproved aliases; all numeric source SOL conversions and relationships held.
3. 149 excluded financial source rows need explicit review decisions. Source monetary exceptions and cleaned formula-relocation independence unresolved.
4. The production-size v2.18 writer must import/export the full source while preserving ALL source A:L/A:AH values, formulas, styles, original other sheets, model header order, and validate EVERY financial amount independently. Large-file artifact_tool import did not complete.
5. Staging Firebase→Flask actual authenticated session, AWS staging DB identity and rollback, independent real-bank same-source oracle and signed Finance/security/owner release remain pending.

**Decision: R267_DEVELOPMENT_ONLY_PASS_WITH_EXTERNAL_FINANCIAL_RELEASE_BLOCKERS. FINANCIAL_APPLY=LOCKED. PRODUCTION_DB_WRITES=0. Production main unchanged.**
