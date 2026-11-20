# D-022 — Consolidated SBI + MXP GST offline review boundary
2026-11-20 — Workstream D · source PR (not an AWS deployment)

## Implements now
- Read-only combination of repository-approved `Invoice Details.` 53/35/34 source contracts, payment-value classification, exact invoice identity duplicate hold, original Column S nonblank exclusion, strict Credit Note report token projection for 53/35, original `PAYMNENT` A–L with Credit I, and optional MXP GST v2.7 batch preview.
- All 53/35/34 source columns and payment A–L values remain unchanged. Outputs anonymized counts/reason codes and source ordinal numbers, not full financial values. The 34-column Credit Note report pathway is explicitly held until approved adapter parity.
- GST integration only consumes separately supplied private master/source records; no private customer datasets in GitHub. GST preview is a **review**, not source authentication or reconciliation.
- Missing/duplicate invoice, source marker S, invalid bank credit, credit note indicator and untrusted GST source are held rather than settled.

## Does NOT implement or certify
- Canonical same-SOL waterfall/full/partial allocations, SBISA SOL 1, DNM-01, date/period/recency/TDS allocation, protected historical ledger, credit-note posting, actual GST source parity, financial database connectivity or production financial operations.
- No actual bank-to-invoice allocation or TDS computation is attempted. Incoming payment source `PAYMNENT` can be summarized from original Column I but *not* matched to invoices without independently authenticated ledger and original row eligibility.
- Returning `REVIEW_REQUIRED` is mandatory even when all synthetic tests pass. The candidate is not finance-release-ready and cannot replace the existing AWS Workspace/backend.

## Private integration requirements
1. Recover or independently reconstruct **approved canonical payment allocator source and rule precedence**, with original historical allocation decisions, suspense/duplicate/error cases and encrypted private fixtures.
2. Load verified source workbook `Invoice Details.` and `PAYMNENT` and authoritative branch master from protected storage, recording independent original-file digest and row-level evidence. GST original-source adapter must prove source identity.
3. Run complete exact 53-column report and approved GST 16-column parity with independent reviewers, including no write and rollback tests.
4. Only then build an isolated AWS zero-financial-write candidate; preserve live Caddy/Firebase/payment states and traffic. Owner approval required for production or finance write changes.

Command for source QA (does not touch finance data):
```
python -m unittest discover -s staging/combined-financial-engine/tests -p 'test_*.py' -v
python -m unittest discover -s staging/mxp-gst/tests -p 'test_*.py' -v
```

**D-022_STATE=OFFLINE_REVIEW_NOT_SETTLEMENT; AWS_DEPLOYMENT=NOT_PERFORMED; FINANCE_CUTOVER=BLOCKED.**
