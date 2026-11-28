# Invoice Creation & GST Reports — Release Gate Evidence and Delta Plan
Date: 2026-11-28
Scope owner: Invoice Creation and GST Reports chat/module only
Status: REVIEW_ONLY / NO_DEPLOY / FINANCIAL_APPLY_LOCKED

## In-scope / out-of-scope
In scope: invoice creation, MXP invoice identity, verified branch/SOL selection, PDF and AWB annexure, correction preview, 16-column GST report contract, service period, source/data parity, invoice-specific Firebase/CSRF acceptance and invoice-only release handoff.
Out of scope: central PostgreSQL schema/roles/migrations (Database Management); allocation/TDS/payment matching (Reconciliation Engine); Caddy/Firebase infrastructure, public ingress and actual production cutover (Deployment/Security module). Dependencies are handoffs, not authority to change those modules.

## Pinned baseline and reuse
- Invoice UI v2 PR #227, exact head `84260273ae06ec080d1748e2f6a902e9d47ce1df`, GitHub Actions run `46120101935`: 140/140 isolated combined tests PASS as reported in PR; unchanged tested code may reuse this scoped evidence. No real AWS authenticated Invoice/GST acceptance implied.
- Invoice/PDF baseline merged PR #182, QA run `45964288949`: 106 combined synthetic/isolated tests PASS at the recorded tested head; owner-approved reference PDF is a design approval, not certified native XLSX pixel parity.
- Historical Credit Note PR #219 (merged), QA run `45968120218`: 123/123 isolated tests PASS, including historical read-only catalog; no authoritative live historical ledger claim.
- QA governance PR #229, exact head `5b8e5aa03fde0694abe5e76647250a972c623aba`, policy QA run `46121397231`: 13/13; combined QA run `46121397195`: 123/123. Still draft and independent.
- Database/security R31 evidence and synthetic loopback TLS evidence may be referenced for matching controls only. They DO NOT certify the Invoice/GST app or close any external release gate.
- For new code/merged SHA: first inspect exact-workflow GitHub Actions receipts. Run only required changed module and integration checks; no automatic blind rerun. If shared workflow itself changes, use fail-closed scope expansion.

## Current actual source guards (PR #227)
- `dashboard_source/invoice_gst_feature.py`: requires invoice-creator permission and CSRF for protected write endpoints; verified branch lookup queries `sbi_invoice_gst.verified_branches` with `verified=TRUE`.
- Finalization requires `SBI_INVOICE_GST_FINALIZE_ENABLED=1`, `SBI_INVOICE_GST_DEPLOYMENT_MODE=ISOLATED_QA`, and `current_database()='invoice_qa'` within the transaction; no production-write enablement.
- Original MXP invoice/correction preview is read-only; replacement finalization is blocked pending immutable correction policy.
- Overlapping finalized multi-month service invoice causes `MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING` for requested monthly GST report; no guessed attribution or double counting.
- These are source checks and isolated CI, NOT proof controls are active on the public preview.

## Invoice/GST gate ledger
| Gate | Existing evidence | Missing acceptance | Owner / next action | Status |
| --- | --- | --- | --- | --- |
| INV-01 QA workflow reconciliation | PR #227 140/140; PR #229 13/13 policy | Both edit `.github/workflows/sbi-invoice-gst-combined-qa.yml`; no combined SHA/QA receipt | Invoice + QA governance reviewers: preserve v2 XLSX path/test and reuse-policy preflight; review resulting diff, only delta QA | BLOCKED_INTEGRATION |
| INV-02 Authenticated invoice endpoints | Offline creator and CSRF tests; shared security R31 reference | Actual invoice-specific approved Firebase creator/viewer permissions, forged/expired session, CSRF, tenant denial, no-write in private AWS QA | Invoice runtime with Deployment/Security support, read-only first | NOT_VERIFIED_RUNTIME |
| INV-03 Approved source data | Private logo/vendor hashes and 4-tab master QA gates in PR #182; subset import strategy | Verified current private vendor profile, approved branch subset, original record provenance in isolated QA, no wholesale promotion of 'WORKING REVIEW — NOT FINAL' master | Invoice source owner; DB team only if schema issue, no main DB changes | PENDING_PRIVATE_EVIDENCE |
| INV-04 Output parity | Approved six-page PDF design; existing PDF/GST contract tests | Actual signed-in invoice PDF, complete AWB annexure, controlled 16-column GST XLSX comparison against original sources on staging | Invoice/GST acceptance; capture redacted receipts, no production finalization | PENDING_PRIVATE_EVIDENCE |
| GST-01 Cross-month service attribution | Current code deliberately blocks overlapping month GST export | Accountant/owner approved treatment for per-month reporting, filing, credit-note reference, reconciliation to taxable totals and no duplicate/omission | Accounting policy decision required before code/test changes | POLICY_PENDING |
| INV-05 Immutable correction | Preview-only reviewed source copying | Authorized revision/credit-note flow: original link, reason, reviewer, audit, numbering and issued-invoice treatment | Invoice/Credit Note module; no overwrite or financial settlement | POLICY_PENDING |
| INV-06 Release handoff | Prior source, isolated QA and guard evidence | Combined SHA, QA receipts, real Invoice/GST E2E, authorized owner decision; deployment owner to approve cutover | Invoice creates evidence packet; Deployment module handles actual release | BLOCKED |

## Next delta QA decision
No source implementation was modified by this document-only checkpoint. Reuse unchanged PR #227 test evidence, and do not dispatch a full 140-test suite because of this documentation.
For merging #227 + #229, select and inspect the combined workflow to retain:
1. Changed-file policy and exact-SHA evidence preflight from #229.
2. The invoice v2 AWB parser Python syntax check and `test_invoice_v2_qa.py` from #227.
3. Correct paths for `dashboard_source/invoice_annexure_intake.py` and `tests/test_invoice_v2_qa.py`.
4. All original fail-closed private-source, GST, credit-note and financial-write-lock assertions.
5. Run only changed-workflow plus impacted module acceptance for the NEW exact integrated SHA (no reuse across SHAs).

## Handoffs (do not implement here)
- Database Management: provide verified private branch/vendor read interfaces and restricted isolated QA `invoice_qa` availability only; do not operate on `sbi_reconciliation_main`.
- Reconciliation Engine: read-only immutable invoice headers and line/audit identifiers for future financial integration; no payment allocations here.
- Deployment/Security: actual authorized Firebase/HTTPS/browser acceptance and final release approval, no Caddy/IAM changes in this module.

Financial Apply LOCKED. Production release BLOCKED. No production writes, migrations, repo merges or deployment authorized by this record.
