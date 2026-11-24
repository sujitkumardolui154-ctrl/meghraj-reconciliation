# SBI v2.51 / Matrix v2.39 — Case 1 owner correction and approved payment-header intake

**Owner decision:** Historical invoice/payment workbook populations, historic row indices and differences in old v2.18 column K statuses are NOT release blockers for rule development. Historical files were supplied to build, explain and test rules; they are not the authoritative new financial ledger. After the complete engine and actual writer are independently certified, the owner will connect them to the main application and upload fresh data for actual reconciliation.

Do not promote historical OK or Duplicate Payment statuses, match by physical invoice rows in unrelated snapshots, or require that fresh data have identical record counts. DO verify same-source financial conservation, rule-specific scenarios, coverage, no double-use of credits, independent calculations and complete executable writer correctness.

## Verified historical and approved payment headers
Historical original PAYMNENT: A Location; B Branch Name; C Txn Date; D Value Date; E Description; F Branch Code; G Name; H Debit; I Credit; J Balance; K Record For Me.
Another historical copy has H Credit. Never assume Credit from a fixed physical position.
Owner-approved full-bank template PAYMNENT: A Description; B Posting Date; C Service Period; D Bank Reference / UTR; E Bank / Statement Source; F SOL ID; G Client Name; H Debit; I Credit; J Balance; K Record For Me; L reserved.
Approved A:K is the canonical **virtual working order** and must not overwrite the original source. An audit retains original column references.

## Approved semantic mapping
- Description / Narration → A Description.
- Txn Date / Posting Date → B Posting Date. Value Date is NOT silently swapped for Posting Date.
- Explicit Service Period → C Service Period when present. If absent, a service month may be separately parsed as narrated evidence, not fabricated by moving columns.
- Bank Reference / UTR → D only when actually present. No invented UTR.
- Bank / Statement Source → E only when actually present. Historical Location is NOT a bank source.
- Branch Code / SOL ID → F, exact text including leading zeros.
- Name / Client Name → G; historical Branch Name is NOT automatically verified customer identity.
- Debit → H; Credit or Credit Amount → I, regardless of physical source column.
- Balance → J; Record For Me → K, regardless of physical source column.

Missing Description/SOL/Credit, duplicate equivalent headers, unapproved guesswork and missing posting date for a full financial read fail closed. Do not treat Debit/Balance as Credit by column position. Missing authenticated bank UTR or source remains a separate provenance gap.

Separate NEW-only three-column upload Description | SOL ID | Credit Amount remains handled under R26.8; it is NOT silently treated as full-bank A:K and lacks authenticated UTR/date unless separately provided.

## Development source updates
- scripts/ci/sbi_case1_payment_header_mapper.py: pure immutable original-column-to-canonical plan, no mutation or finance Apply.
- scripts/ci/sbi_r266_readonly_real_source_population_gate.py: Credit and SOL resolved by header instead of physical I/F; records mapped source positions in audit.
- scripts/ci/sbi_r267_readonly_real_source_adapter.py: posting date, description, SOL, client, period and protected Record For Me resolved by header, with unverified evidence quarantined.
- tests/test_sbi_case1_payment_header_mapper.py: ambiguous headers, legacy H/I, approved A/I, synthetic order permutations, and no historical status copying.
- tests/test_sbi_case1_payment_header_integration.py: synthetic full workbook read-only source intake and review-planner integration in both supported layouts.

## Certification decision
CASE1_HISTORICAL_DIFFERENT_POPULATION_AND_K_STATUS=REFERENCE_ONLY_NOT_BLOCKER.
Still mandatory: complete v2.51/v2.39 executable financial accounting and full method parity on controlled scenarios; actual v2.18 writer correct monetary values at full size; signed Finance/security/owner release. No historical finance statuses imported.

FINANCIAL_APPLY=LOCKED; PRODUCTION_DB_WRITES=0; NO LIVE BANK SETTLEMENT.
