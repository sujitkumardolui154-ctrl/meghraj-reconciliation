# Stage R26 — Independent synthetic financial-rule oracle (24 November 2026)

**Strict release decision:** `R26_DEVELOPMENT_SYNTHETIC_QA=SCOPED_ONLY`, `MASTER_V251_PRODUCTION_CERTIFIED=NO`, `FINANCIAL_APPLY=LOCKED`.

## Actual sources directly inspected

1. [User-authored 28 Oct Master v2.51/Matrix v2.39 repair blueprint](https://docs.google.com/document/d/1wrM3PtBI1MHzowVGdtTl8pl32xNk_SzLYBwbJDI8GIk/edit): a stage-by-stage **repair specification**, explicitly not a runnable or approved financial engine. Requires single Master-owned global ledger, separate Finance approval and waterfall LAST.
2. [28 Oct OUT-SCHEMA-V218-001 approved layout](https://docs.google.com/document/d/1SPAHhP4K2T1jjAW7goXfUz7J9dtihzpc/edit): immutable source PAYMNENT A:L and Invoice Details. A:AH; output columns M:W and AI:AM; no historical OK-copying.
3. [10 Nov reconstructed rule decisions](https://docs.google.com/document/d/1Lb-q81sn2VRa8wYZwejsTQer3aZkqrbUKFhrsTMjBFM/edit): historic reported v2.51 controls (some source signatures still outstanding), service-period PRM-01, SBISA, GST later, DNM-01, duplicates and controlled ledger.
4. [R25 source/master QA](docs/SBI_R25_COMBINED_SOURCE_MASTER_PRIVATE_QA_20261124.md): private original/cleaned workbook integrity, 149 excluded rows, two different Drive SOL masters with identical official key/name mapping but lacking verified owner approval.
5. Current GitHub development tree was inspected for full v2.51/v2.39 executable; only bounded R15–R25 source/read-only/test modules and staging read-only workflow could be verified. The locally recovered historical `reconciliation_engine.py` says **v2.22 / Matrix v2.10**, which must NOT be substituted for the v2.51 runner. Historic recovered `conservative_engine.py` is partial rehearsal, not full v2.51.

## R26 synthetic-only scope

New `scripts/ci/sbi_r26_independent_financial_oracle.py` and `tests/test_sbi_r26_independent_financial_oracle.py` have **no real Excel, cloud, bank or SOL master access**. Every candidate uses a `SYN-MXP-` or `SYN-PAY-` identifier. The module is NOT the full financial engine and cannot be loaded as a production reconciliation implementation.

Fixtures exercise:
- Exact decimals, TDS 0%/1%/2%/3% on taxable with ROUND_HALF_UP; cross-check with R17 review-only TDS math. No unsupported 4%/5% rate, subcent or binary float accepted.
- Same-SOL/official-name matching, MXP exact-reference discrepancy, chronology, service period including text multi-month, protected original invoice S (nonblank including zero), original bank K, SBISA blank invoice SOL and unauthorized cross-SOL.
- GST-later flagged for separate source-ledger proof. Amount resemblance is never sufficient to write financial OK.
- Independently proposed global graph capacity: duplicate invoice IDs, duplicate payment IDs, repeated edges, no over-reservation of bank credit or invoice outstanding, and check that waterfall is NOT run before global adjudication or revisited afterward.
- Cross-source status comparison gated on identical exact source SHA; prior v2.18 provisional OK 272-case difference cannot be treated as approved status parity.
- Release status returned **fail-closed** regardless of caller inputs. All outputs are `REVIEW/HOLD`; no real finance writes or `OK` assignments.

## Correct integration order in spec

Fresh attachment & SHA → original Excel contract → authorized version-pinned master → invoice identity and original S eligibility → exact reference and month/date/money/TDS → documented GST/SBISA/child exceptions and DNM review → one global Master-owned reservation ledger → waterfall LAST → final GST/duplicate validation → v2.18 writer unchanged source → independent same-source full-engine parity → staging auth/db rollback → explicit Finance/security signoff and user cutover.

## Pending for actual full-engine certification

- **Master v2.51 / Matrix v2.39** complete executable binary/source tree, repository location, pinned SHA and independent QA signoff not located in directly examined sources; do **not** infer existence from a blueprint or version label.
- Complete financial method parity must include real full and partial allocations, cross-SOL exceptional relationship authority, SBISA, narrated GST, DNM-01 parameters (±₹10 search, best delta ≤₹1, next ≥₹2 away, ≤180 days), multi-month, global ledger, waterfall, false OK protections, independent net/gross/TDS oracle and all rulebook versions.
- Latest SOL master authority not selected; 10 missing-SOL master rows and 3 padded collisions unresolved. Leading-zero candidate identities are review-only; 105 of 111 excluded numeric-SOL invoices have candidate official-name matches; owner reinstatement pending.
- 149 excluded rows remain in private audit; **not certified false/invalid**. No private SBI transaction rows were committed into GitHub.
- Real v2.18 money-parity writer, 53-column financial report parity, actual authorized Firebase→Flask session, real AWS staging PostgreSQL read-only permissions, backup/rollback and signed Finance/security cutover are not independently verified.
- This partial R26 development gate does NOT change the eight R21 required external release obligations.

**No production main update, database write, actual payment allocation, historical OK copy or unauthorized master normalization is permitted.**
