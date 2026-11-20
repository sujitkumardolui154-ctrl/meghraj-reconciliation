# SBI AWS Reports — Source-certified read-only connection (20 November 2026)

## Owner problem
SBI Reconciliation Dashboard → Reports tab showed HTTP 403 and disabled CSV downloads.

## Root cause
The AWS Firebase Login / Evidence application intentionally maps /api/reports to its
generic 403 finance API denial. The frontend still requests a legacy GCP v1.4.2
report catalog that was never connected to a verified AWS data source.
The separate aws-backend-readonly candidate intentionally has no financial database
and returns 503 for reports until approved data are independently mounted.

## Source-only fix
- New GET /api/reporting/v2 returns authenticated read-only source catalog.
- New GET /api/reporting/v2/{unpaid,ok,error-value,balance-review}.csv exports
  only independently approved, immutable, SHA256-verified private CSV files
  with exact 53-column header digest, verified row counts and approval receipt.
- No snapshot configured: 200 catalog NOT_CONNECTED, per-report NOT_CONNECTED,
  CSV fail-closed 503; frontend shows source reason instead of blanket 403.
- User cannot see any invoice counts until a verified data source is connected.
- Preserves ORIGINAL 53 source headers, including duplicate Branch Code and
  Client Name (their order is pinned by independent header SHA256).
- Negative numeric source values remain intact; dangerous CSV formula strings
  must be escaped before any source output is approved.
- Existing /api/reports finance route stays denied by design; no financial writer,
  importer, allocation engine, fake invoice status or Firebase admin action added.
- Financial writes and production reconciliation remain blocked.

## Data activation prerequisites
An independent finance reviewer must approve a private non-expired immutable
manifest with schema sbi-aws-phase1-private-snapshot/v1, source SHA256,
approval receipt and 53-column header SHA256; CSV files must be verified
against the original invoice snapshot and current completed imports.
The next staging release must mount the approved private source directory
read-only (not bundled in GitHub or Docker image), inject separately controlled
environment pins, and test authenticated report parity before activating
CSV downloads. Do not claim that report v1.4.2 live Firestore data is connected.
No source data or financial API credentials were retrieved by this change.

## Security
No new scheduled automations. Preserve Caddy, Firebase, Control Tower,
separate personal notes, payment evidence volume and /pipeline Basic Auth.
Do not modify any live financial database.
