# SBI Workspace — Module Development QA Execution Policy v1

Owner rule effective 28 November 2026. Governance only. No authorization for production deployment, main DB writes or financial Apply.

## Mandatory checklist BEFORE any QA or rerun

1. Check GitHub repository for the existing module workflow, the exact PR HEAD commit SHA and completed GitHub Actions run evidence for that SAME SHA and workflow.
2. Reuse an existing completed successful run for that exact unchanged SHA and workflow, provided its tested scope and environment match. Earlier SHA, different workflow, synthetic-only or failed/cancelled evidence is NOT a substitute.
3. Run only changed-module tests, not automatic full QA. Use the conservative selector in tools/qa_module_policy.py. Changed shared APIs, DB schema, authentication, master data, new/unrecognized files, or unknown diff expand scope. Deleting tests also counts as a change.
4. When a run fails, read its failed job/logs first. Rerun only a failed job when a retry is needed; after a source fix, test the new commit and affected modules. Never rerun successful suites reflexively.
5. If GitHub status cannot be checked, or a workflow is absent, do not claim that QA passed. Missing workflow BLOCKS acceptance; missing GitHub receipt causes the relevant tests to run instead of skipping.
6. Keep QA/testing inside separate development module workflows, with deployment acceptance in independent protected release stages. Documentation-only changes must not repeat 140 invoice/GST tests.
7. Mandatory external release tests are non-substitutable: real Firebase distinct owner/tenant authentication, external HTTPS/mTLS, PostgreSQL roles/RLS, historical invoice and credit-note coverage, GST filings, bank payment reconciliation and owner authorization. A synthetic pass does NOT cover those gates.
8. No testing policy may enable writes to sbi_reconciliation_main, bank/payment records or historical GST filings. Isolated QA financial fixtures are allowed only in invoice_qa under existing safety controls.
9. Stage progression is CODE_CHANGED -> MODULE_QA_REQUIRED -> MODULE_QA_PASS -> PRIVATE_INTEGRATION_QA -> OWNER_DEPLOYMENT_APPROVAL. No automatic promotion or production deployment.
10. Always record the run ID/URL, exact SHA, module scope, test count, conclusion, and whether financial writes and deployments occurred.

## QA ownership

| Changed module | Development QA | Independent release requirements |
|---|---|---|
| Invoice, Excel annexure, branch lookup | invoice_db, invoice_ui; GST, master and private-source tests when affected | Verified private SBI branch/vendor data; multimonth GST policy; audited correction approval |
| Credit Note Generator | credit_note, historical; invoice when the interface changes | historical credit ledger, GST filing and payment evidence, distinct credit-note creation permissions |
| GST contract | gst plus dependent invoice tests | accountant-approved taxable-month attribution and filing review |
| Historical source | historical read-only source and catalog QA | verified Firestore/PostgreSQL authoritative evidence and real authentication |
| Shared auth/gateway, private source or schema | all relevant combined financial modules | Firebase owner isolation, RLS and external security QA |
| Railway preview | railway-preview-safety.yml | separate deployment acceptance |
| AWS Lightsail preview | aws-lightsail-preview-check.yml | external approved HTTPS/mTLS and separate deployment acceptance |
| Migration/public-source safety | migration-safety.yml | privileged migration approval; no bypass |
| QA rule code and unit tests | sbi-module-qa-policy.yml | no deployment approval derived from these tests |

The existing combined invoice/GST workflow selects changed groups rather than unconditionally running every suite. Paths without a known mapping run full QA (fail closed). If a required run is already successful at the exact commit, it can be cited without another execution. Deployment tests remain independent and must not be bypassed.

## Read-only operator check before rerun

- Verify 'git rev-parse HEAD' and the intended branch.
- Check existing workflows using 'git ls-files .github/workflows'.
- Run the selector with exact base and head SHA:

    python3 tools/qa_module_policy.py --base-sha FULL_BASE_SHA --head-sha FULL_HEAD_SHA --repo sujitkumardolui154-ctrl/meghraj-reconciliation --check-github

The preflight sends only GitHub API GET requests and does not run QA. It can use GITHUB_TOKEN with actions:read rights from a secured terminal, but never reveal credentials. Interpretation: REUSE_APPROVED_EXACT_SHA_QA means no redundant rerun; RUN_SELECTED_QA means only selected modules; NO_INVOICE_QA_REQUIRED means no invoice module changes; BLOCK_REQUIRED_WORKFLOW_MISSING means stop and repair the workflow definition.

## Existing verified snapshot (not future authorization)

Before adopting this policy, Invoice UI v2 PR #227 at head 84260273ae06ec080d1748e2f6a902e9d47ce1df had successful combined isolated QA (140/140), AWS Lightsail preview safety, Railway preview safety, and migration safety. Reuse that exact-commit evidence; future commits require fresh verification.

**Production financial writes LOCKED. No deployment initiated.**
