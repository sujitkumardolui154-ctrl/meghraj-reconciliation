# Generate Credit Note — SBI Reconciliation Workspace (27 Nov 2026)

**Owner request:** Separate credit-note generator in Reports. Credit Note No. and Credit Note Date must be entered **manually**; original invoice details must be fetched from the database. Preserve the owner-supplied tabular credit-note format, including multi-invoice rows and GST totals.

**Original source:** Uploaded `Pasted markdown(1).md` containing the earlier Meghraj Express credit note layout, reference Credit Note No. `MXP/2026-2027/01`, date shown as `31/05/2026`, 508 source invoice rows, SAC 996812, state code 19, SBI GSTIN `19AAACS8577K3ZK`, supplier Meghraj Express, GSTIN `19ACSPR2953D1Z5`. Sample records are **not** inserted into the database and are not treated as authoritative. Source also has extraneous text `16/03/2016` next to the date label: never infer the issue date from it.

## Source arithmetic check

The 508 sample taxable amount cells sum to `529931.32`. Therefore:
- CGST at 9%: `47693.82`.
- SGST at 9%: `47693.82`.
- Credit note total: `625318.96`.
- Rounded display: `625319`.
The attached source displays subtotal `529931` (omits `.32`) but its GST and grand total agree with the **true** 508-row taxable sum. The implementation uses exact Decimal/HALF_UP and does not copy an inconsistent displayed subtotal.

## Proposed user workflow (implemented in QA branch)

1. Reports > **Generate Credit Note — Meghraj Express**.
2. Manually enter credit note number (e.g. `MXP/2026-2027/01`) and credit note date; both mandatory. FY in number must match note date. **No automatic number allocation.**
3. Provide a mandatory reason, then paste rows `Invoice No[TAB]Credited Taxable Amount` (up to 1,000 rows). Manual credit taxable values allow full or partial credit.
4. Click **Fetch Original Invoice Details**. The backend fetches each original invoice number, invoice date, service month, verified branch/customer, SOL, GSTIN, original taxable, prior issued credit notes and remaining credit balance from PostgreSQL. No invoice date/month/customer amount override is accepted.
5. If an invoice is missing from the isolated registry, fails verification, has an existing cancellation, mixes SBI Bank and SBI Fund GSTINs, or exceeds remaining credit balance, **block**. No guessed data.
6. Preview the credit note amounts, CGST 9%, SGST 9%, total. Preview performs NO DB write.
7. Only after QA authorization, finalize and save a **new** append-only credit note and linked source-line snapshots in PostgreSQL. PDF renders the owner's source columns and financial totals using the privately verified Meghraj Express profile/logo. The original source invoices remain unchanged.
8. No payment reconciliation, customer ledger posting or GST filing is performed by this module.

## PostgreSQL architecture

- Existing schema: `sbi_invoice_gst` (not a second master production DB).
- New QA migration: `staging/invoice-gst/005_credit_note_registry.sql` (after migrations 001–004).
- Tables: `credit_notes` (note number/date, class/GSTIN, tax, totals, actor/time, immutable) and `credit_note_lines` (per-invoice link, factual original invoice snapshot, original taxable, manually approved credited taxable).
- Read-only derived view: `credit_note_invoice_credits` tracks previous credits, blocking over-credit.
- All source invoice locks acquired deterministically at finalize; duplicate credit note numbers rejected. Credit note and invoice evidence cannot be silently modified/deleted.
- API: `POST /api/credit-notes/lookup`, `POST /api/credit-notes/preview`, `POST /api/credit-notes/finalize`, `GET /api/credit-notes/pdf?no=...`.
- Dedicated Firebase claim `sbi_credit_note_creator`, CSRF, and feature flags `SBI_CREDIT_NOTE_ENABLED`, `SBI_CREDIT_NOTE_FINALIZE_ENABLED`.
- The **finalize** route is hard-locked to deployment mode `ISOLATED_QA` and database name `invoice_qa`. No production finance writes have been authorized.

## Live release blockers

This isolated module can currently retrieve original invoices **only from** `sbi_invoice_gst.invoices`. The owner's historical multi-year sample invoices in the main reconciliation store are not automatically available. Before live use, build and approve a verified READ-ONLY source adapter to the authoritative historical invoice summary without bypassing source conflicts, duplicate invoice evidence or original master-verification flags. Integrate existing credit-note and payment/GST filing status to protect against previously issued adjustment notes and double credit.

Legal/tax/accounting review must decide how and when this actual credit note modifies GST output and settlement ledgers. Never silently rewrite already-filed GST returns, originals, bank payment evidence or reconciliation allocations. PDF styling approximates the uploaded markdown layout; a native original credit-note PDF/XLS was not provided for pixel-identical visual certification. Keep PR #182 draft; separate owner production authorization required.

## QA

CI runs `tests/test_credit_note_qa.py` with synthetic PostgreSQL 16 under `invoice_qa` and verifies required manual inputs, source lookup, multiple invoice rows, full/partial credits, tax totals, PDF content, duplicate notes, immutable history, permission/CSRF and approved-live denial. No real source records are used.

## Credit-note legal-document preflight (Rule 53)

The applicable Indian CGST Rule 53(1A) specifies a serial no. **not exceeding 16 characters**, unique within the financial year; the system enforces this in the manual form, backend contract and PostgreSQL CHECK. Reference:
https://cbic-gst.gov.in/gst-invoice-rules.html and
https://taxinformation.cbic.gov.in/content-page/explore-rules/1000144/1000001.

The owner's sample format `MXP/2026-2027/01` is 16 characters. The `/100`
variant is too long and is rejected; a different *approved* shorter series is
required if more than 99 notes are issued under that numbering scheme. No
automatic numbering is applied.

Before issuing a legally operative live document, verify the recipient's
complete registered legal address and confirm all Rule 53 particulars
(including supplier and recipient details, original invoice numbers/dates,
taxable value and credited tax/rate, signatory). The supplied markdown credit
note has no customer mailing/address line, so do not treat its layout as a
complete legal certification without private verified address evidence.
