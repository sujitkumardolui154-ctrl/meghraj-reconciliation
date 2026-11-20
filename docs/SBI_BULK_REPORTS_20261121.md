# Bulk Report — Reports tab, source-only Excel generator (21 Nov 2026)

Owner request: Rename "Excel Upload — Dashboard v1.3.0" to **Bulk Report**,
move it from Database Update into the Reports tab, repair and enable its button.

## Result
- Existing disabled financial POST /api/upload removed from UI. Legacy
  financial API remains denied (403).
- New authenticated/CSRF protected POST /api/bulk-report/generate accepts a
  single invoice XLSX <=8 MiB, <=20,000 source rows with exactly one approved
  34/35/53 original header layout. No client-supplied column remapping.
- Returns ZIP with All Invoices, Unpaid, OK Payment Value, Error Value,
  Balance Review and Validation Review CSVs and SHA256 source manifest.
- Invalid, duplicate, numeric or missing invoice IDs are excluded from
  accepted categories and appear in Validation Review. Preserve original
  SBI 53-column order with duplicate Client Name and Branch Code columns.
- Amount classification mirrors read-only source rules: blank or zero unpaid,
  positive numeric OK value, negative/invalid/formula error-value. OK is not
  evidence of fully paid. Missing/invalid balance enters Balance Review.
- All CSV cells escaped against formula injection. No Excel formula is
  executed. Processing only in memory; no uploaded workbook is persisted.
- The separate certified /api/reporting/v2 remains source-approved only and
  DOES NOT become populated from ad-hoc Bulk Report uploads.
- Existing Database Update invoice preview and Payment Evidence uploads
  remain separate. Financial writers and reconciliation execution disabled.

## Rollout
Standalone AWS blue/green candidate needed. Exact baseline must be the
currently deployed source Reports Caddy; do not activate while it differs.
Keep private evidence/workspace mounts and Firebase credentials unchanged.
Prior 909 MiB RAM server needs 2 GiB swap verified and staged before build.
No scheduled automations resumed, no financial database writes.
