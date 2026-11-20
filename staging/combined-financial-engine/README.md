# Combined SBI Reconciliation Engine — integration scope and status

Workstream D | owner-requested combined engine | review only

## Intended unified workflow
Invoice source (immutable A-L and invoice Column S exclusion) -> verified branch/SOL/master -> payment data (PAYMNENT credit Column I, narration date/month, same-SOL matching) -> deterministic allocation/TDS and exception handling -> protected Credit Note handling -> independently sourced MXP GST Preparation v2.7 (all v1.8 mandatory invoice checks) -> reconciliation and GST report contracts -> authenticated SBI Reconciliation Workspace.

This is **one financial application**, not separate settlement engines. GST Preparation remains a separately testable, read-only preparation function until authorized.

## Actual recovered modules in this GitHub repository
- `backend_source/invoice_source_schema.py`: supported source layouts and invoice field positioning.
- `backend_source/payment_report_rules.py`: read-only payment value classification, **not payment allocation**.
- `backend_source/credit_note_53_adapter.py`: read-only Credit Note report projection, **not posting**.
- `backend_source/reconciliation_changes_offline.py`: read-only comparison of independently supplied snapshots, **not settlement**.
- `staging/mxp-gst/`: alias resolver, preview, batch duplicate validation and integrity prechecks. Requires private master/original invoice evidence and authenticated source bytes.
- `staging/combined-financial-engine/readiness_gate.py`: strictly release evidence assessment, **not a reconciliation engine**.

## Outstanding technical blocks
1. Recover and attest canonical deployed payment reconciliation source and approved rule precedence (same-SOL full/partial waterfall, service-month intelligence, SBISA SOL 1, DNM-01, 180-day, TDS, protected historical allocations and suspense).
2. Confirm trusted private source/master and manifest SHA256 by independently controlled inventory, and exact invoice-to-original/report parity.
3. Attest published AWS immutable image identity and actual financial API logic. Operator observed `/healthz=200` and `/readyz=503`; readiness cause is not proven.
4. Confirm legacy invoice schema and GST 16-column output contracts across report, backend, and Workspace auth boundaries. Run integration and regression suite with independently owned data fixtures.
5. Verify deployment backup, rollback, zero-write boundary, and authenticated isolated staging. No changes to Caddy, Workspace, Firebase, existing payment allocations or production financial data until gates are met.

## Manual rectification
All rule conflicts / non-unique SOL / duplicate invoice / source mismatch are REVIEW_REQUIRED. Report in the ChatGPT workstream; approved code corrections go to isolated PR with regression QA. New rule precedence or production financial actions require separate owner approval.

**CURRENT: COMBINED_ENGINE_COMPLETE=NO; SOURCE_CONTRACT_TESTS=PARTIAL; AWS_WORKSPACE_DEPLOYMENT=NOT_PERFORMED; FINANCIAL_WRITES=DISABLED; PRODUCTION_CUTOVER=BLOCKED.**
