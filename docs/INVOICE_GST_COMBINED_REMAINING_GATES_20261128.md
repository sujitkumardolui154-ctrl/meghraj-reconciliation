# SBI Invoice Creation + GST Report — One-command combined remaining-stage preflight
Date: 28 November 2026. Scope: Invoice/GST ONLY. No deployments or financial writes.

## Evidence checked BEFORE adding this stage
INV-01 PR #235 previously passed five GitHub workflows on SHA `2375eb71d02b07adaedd1350efc385000d48291d` (Invoice/GST combined, selective QA policy, AWS-preview safety, Railway safety, migration safety). Its branch subsequently advanced to `45dc2b9bf56910acf2c1a533b4d0ca8cb9a591e4`; the newer Invoice/GST run must be checked by exact SHA before treating it as reusable. This branch is based on that newer commit, but contains only NEW combined-readiness code and focused tests; DO NOT rerun previously successful unrelated financial or AWS acceptance suites.

## Existing modules reused, not reimplemented
- `scripts/sbi_invoice_gst_aws_staging_readiness.py`: source SHA256/vendor bundle/PDF, optional isolated `invoice_qa` metadata-only checks, optional unauthenticated preview check.
- `scripts/sbi_invoice_gst_private_qa_gate.py`: canonical fail-closed source/QA prerequisite decision.
- `tools/qa_module_policy.py`: module-local exact-SHA GitHub Actions reuse policy.
- GitHub Invoice/GST isolated CI and existing private-source/master tests are retained unchanged.

## Single combined command (read-only operator mode)
Run on an **authorized isolated staging machine** only after checking existing exact-commit QA and verifying that the listed private artifacts are present. Do not pass passwords, bearer tokens, DSNs, or private file contents into chat or GitHub.

```bash
python scripts/sbi_invoice_gst_combined_readiness.py \
  --master /private/SBI_SOL_Branch_Master_FINAL.xlsx \
  --vendor-bundle /private/Meghraj_Invoice_Private_Assets_With_Full_Header_20261124.zip \
  --approved-pdf /private/Meghraj_Express_MXP18430_Corrected_Full_Header_Invoice.pdf \
  --qa-db --check-public-ingress \
  --output /private/sbi-invoice-gst-combined-readiness.json \
  --assert-source-ready
```

An existing signed-off source preflight can be reused without rereading sources, database or public ingress:
```bash
python scripts/sbi_invoice_gst_combined_readiness.py \
  --preflight-json /private/sbi-invoice-gst-private-qa-preflight.json \
  --output /private/sbi-invoice-gst-combined-readiness.json \
  --assert-source-ready
```

Return codes: 0 = source prerequisites ready for **further manual authorized real test** (never production); 2 = source prerequisites missing; 3 = invalid/unavailable evidence. Output contains no raw customer rows or passwords. If source paths are not supplied, readiness is blocked, not fabricated.

## Independent acceptance that this command NEVER marks PASS
- INV-02: real signed Firebase creator/viewer/anonymous requests on exact invoice endpoints, CSRF negative, unauthorized tenant denial; reuse matching dedicated security-module evidence but test invoice-specific missing cases.
- INV-03: independently verified per-row master identity/billing issuing location, unambiguous SOL/GSTIN and private vendor header; master is `WORKING REVIEW — NOT FINAL` and cannot bulk-import.
- INV-04: authenticated approved six-page invoice PDF, complete AWB annexure, GST 16-column Excel, exact original source parity; original native XLS visual parity is not established.
- GST-01: owner/accountant approval of cross-month service vs GST reporting period, no double count; code remains blocked with `MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING`.
- INV-05: immutable correction event, reason and reviewer, credit-note/GST filing dependency and historical payment evidence; source invoice cannot be overwritten.
- INV-06: separate owner release approval after all external acceptance and handovers. Database team owns DB migration and role grants; Reconciliation team owns allocations; Deployment owns external HTTPS/Firebase operations.

## QA scope and non-bypass
Only new `tests/test_invoice_gst_combined_readiness.py` plus `scripts/sbi_invoice_gst_combined_readiness.py` are targeted by `.github/workflows/sbi-invoice-gst-readiness-qa.yml`. This is OFFLINE unit QA (mocked DB/HTTP), not AWS acceptance. Never treat an offline PASS as proof of remote Firebase auth, DB source import, PDF parity, accounting approval or production security. No automatic release.
Financial Apply LOCKED. Production release BLOCKED. No code changes to Database/Reconciliation modules and no production writes.
