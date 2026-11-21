# Production Deployment Gate — not yet satisfied

**Do not merge/release to financial production solely because 40 synthetic tests passed.**

1. Reviewed code and authenticated new-only source authority. A three-column `Description | SOL ID | Credit Amount` spreadsheet is insufficient to prove bank-date, UTR and origin; separately signed metadata/source receipt is mandatory.
2. Approved master and independently protected new-only invoice/credit-note input. No access to pre-cutoff invoice, payment, suspense, GST or historical allocation tables. No backfill.
3. Exact v2.51 methods not yet implemented: GST-separated and base-only accounting modes, approved rate/priority evidence, parent-child SOL exceptions, complete MXP source reference policy, independent DNM-01 resolution and globally unique allocation rule.
4. Atomic writer with durable UTR and receipt hash constraints, explicit privileges and immutable audit, separate isolated new-only DB. Test duplicate/concurrent writers in that isolated database.
5. Rebuild known QA-failed v2.18 XLSX output writer; verify numeric/text identity fidelity, source-column preservation, one-workbook rule.
6. One consolidated *independent synthetic end-to-end* QA gate for new-only input -> matching -> ledger -> v2.18 output, permission-denial, rollback and current AWS authentication/routing.
7. Owner must explicitly approve a separately identifiable finance-write release after the above evidence passes. Until then, `Apply Reconciliation` remains disabled on both client and server.

**Existing AWS application was not changed by this package.**