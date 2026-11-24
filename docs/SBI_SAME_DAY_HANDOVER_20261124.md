# SBI Reconciliation — Same-Day Technical Handover, 24 November 2026 (IST)

**Requested deadline:** 24 November 2026, Kolkata. **Handover class:** development and read-only operational material with explicit open financial release gates. **Production-financial release:** BLOCKED, `FINANCIAL_APPLY=LOCKED`.

## Snapshot and hard distinction

| Area | Development evidence available | Production release assertion |
|---|---|---|
| R13 | 89 offline/emulator authentication and payment-evidence tests, previously passed | No real financial authentication to production engine |
| R14 | Draft PR [#154](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/154), guarded manual sbi-r9-staging Firebase signed-token→actual Flask session probe | Real authorized Cloud Shell execution **NOT YET VERIFIED** |
| R15 | Original `PAYMNENT` / `Invoice Details.` intake, source credit I, protected S | Historical workbook is not a fresh execution source |
| R16 | Exact text SOL + official identity shadow, ambiguous/duplicate protections | Current approved SOL master is NOT signed into this release |
| R17 | Decimal HALF_UP TDS, DNM-01, SBISA, GST and capacity review-oracle synthetic tests | No settled payment or final waterfall signoff |
| R18 | Exact v2.18 protected A:L/A:AH and model M:W/AI:AM structural comparison; 53-column invoice report contract | Actual v2.51 writer outputs/financial parity NOT VERIFIED; review PR #158 remains separate |
| R19 | 174/174 tests passed across R15-R19, synthetic in-memory source-to-output rehearsal | No real bank data or v2.51 executable certification |
| R20 | Actual synthetically limited review XLSX serializer; disposable CI-only PostgreSQL connection, read-only role, rollback and capacity checks | No real PostgreSQL server/snapshot, no live writer or financial allocations |
| AWS reporting | User's prior evidence reports generated on preview; prior database backup audit for main/staging PASS | This QA did not independently re-query AWS, SNS or S3 today; no financial API cutover |
| Production Firebase | Real signed token tests reported in R12; R14 full app session pending | No real signed token acceptance by actual Flask session independently proven |

**Warning:** Successful *synthetic* reconciliation checks do not equal a certified, payable financial ledger. The new production financial database should remain free of historical imported payments/invoices unless separately and explicitly authorized. Do not reuse historical v2.18 reconciled output as fresh bank evidence.

## Source of truth and branch chain

Repository: [meghraj-reconciliation](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation).

- Development readiness branch: `feature/sbi-payment-reconciliation-readiness-gate-20261120`; production `main` is not the financial release branch.
- R18 draft PR: [#158](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/158). R19's PR #159 was merged into the **R18 review branch**, not production.
- R20 branch: `review/sbi-r20-deadline-handover-combined-20261124`, created from latest R18 review branch with R19 combined QA included. R20 PR is a stacked development review, not cutover authorization.
- R14 separate manual-authentication draft PR: [#154](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/pull/154).

## Exactly which items can be handed over today

1. **GitHub source:** R15–R19 validators and independent synthetic regression cases; R20 review-only Excel serializer and disposable CI PostgreSQL probes, fully inspectable and reproducible.
2. **CI evidence:** run the R20 combined workflow and save its exact HEAD SHA, execution URL, each test count and PostgreSQL result. Keep earlier failed R19 (blank-cell identity and self-comparing 53-header) and failed R20 (Docker private bridge IP recognition) runs in the history; do not hide defects. Never claim PASS until green exact-head logs are inspected.
3. **Synthetic workbook example:** safe to share only when labelled `SYNTHETIC — NOT AN SBI RECONCILIATION`; all model payment statuses remain `SUSPENSE`. No private real bank data should appear in GitHub or downloadable artifacts.
4. **Read-only reporting:** existing AWS preview/report functionality can be used independently of the financial engine, subject to normal user access and live operations verification.
5. **Backup operations:** prior owner evidence for `sbi_reconciliation_main` and `sbi_reconciliation_staging` found local archive/S3/KMS/metadata and backup monitor PASS and scheduled run evidence. This is **historical owner evidence**, not a fresh independent backup verification performed by R20.

## Exact instructions for authorized owner: close R14 independently

Work only in owner-approved **`sbi-r9-staging` Google Cloud Shell** with private, keyless service-account ADC for `sbi-r9-qa@sbi-r9-staging.iam.gserviceaccount.com`. Never paste secrets into chat or GitHub. The complete gated probe and required account claim are documented in the [R14 instructions](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/blob/review/sbi-r14-real-firebase-app-session-readonly-20261124/docs/SBI_R14_REAL_APP_SESSION_READONLY_20261124.md).

```bash
git fetch origin review/sbi-r14-real-firebase-app-session-readonly-20261124
git switch --detach FETCH_HEAD
export GCLOUD_PROJECT=sbi-r9-staging
export SBI_R14_REAL_APP_SESSION=R14_REAL_STAGING_APP_SESSION_READONLY
read -r -s -p "Approved synthetic SOL key(s): " SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS; echo
export SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS
python scripts/ci/sbi_r14_real_app_session_readonly.py
unset SBI_R14_REAL_APP_SESSION SBI_R14_APPROVED_SYNTHETIC_SOL_KEYS
```

If ADC, preapproved QA test user or required claims are unavailable: record **BLOCKED**, not PASS. **Do not** add privileges/user claims solely to force a green check. R14 verifies Flask in-process session, *not* AWS public login/TLS.

## Critical separate financial acceptance checklist

**All rows below remain blocked until separately evidenced by authorized owners; none can be automated away by a synthetic CI pass.**

| Gate | Required evidence | State |
|---|---|---|
| FFI-001/FRESH | Original newly provided SBI financial workbook with source-attachment provenance and approved exact SHA | PENDING |
| SOL MASTER | Latest approved SBI official branch master & aliases, exact SHA and independent signoff | PENDING |
| FINANCE CODE | Complete executable Master v2.51 / Matrix v2.39, signed source tree SHA plus independent method-coverage ledger | PENDING |
| MATH & ALLOCATION | Same SOL waterfall, partials, TDS 0/1/2/3%, DNM-01 nearest dominant, SBISA SOL 1, multi-month, GST-later, cross-SOL exception approvals, global uniqueness, duplicates/credit notes | PENDING |
| WRITER | Actual signed v2.18 Excel writer against same-source reference, exact 53-column report money parity and source immutable proof | PENDING |
| DATABASE | Real isolated staging PostgreSQL DB read-only snapshot and transaction rollback + auth chain, **without** production writes | PENDING |
| AUTH | R14 signed Firebase ID accepted by actual Flask session, CSRF, cookie, read-only API, Apply denied | PENDING |
| APPROVAL | Authorized Finance/security acceptance, rollback rehearsal and documented cutover decision | PENDING |

## Recommended immediate disposition for 24 November

**HANDOVER: DEVELOPMENT & READ-ONLY REPORTING, WITH KNOWN FINANCIAL BLOCKERS.** Provide GitHub review PRs, combined QA logs/artifacts, current backup/audit references, and this acceptance checklist. **Do not state that the financial reconciliation engine is deployed or live.** Keep real financial Apply disabled, historical production DB empty of bank sources and production routing unchanged. The missing full v2.51 source and signed finance evidence are real blockers, not formatting or CI issues.
