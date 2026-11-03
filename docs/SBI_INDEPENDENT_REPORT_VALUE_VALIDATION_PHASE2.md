# SBI Independent Report-Value Validation — Phase 2 (SOURCE ONLY)

## Scope and status

**Implemented:** an independent offline value checker for the original
53-column invoice snapshot against the 18-column Credit Note export, plus
existing independent 53-column primary partition parity tests. Source code,
synthetic fixtures and GitHub CI contain **no private financial records**.

**Not completed:** no authenticated production Firestore export or verified
private original/report CSVs were available to this GitHub workstream. A green
synthetic test is not real parity evidence and cannot authorize deployment.

Financial execution remains restricted. Do not alter the current dashboard,
AWS runtime, payment reconciliation engine, original CSV, or approved headers.

## Provenance requirements (operator-controlled, private runtime)

For a meaningful live-source-to-report validation, acquire separately
reviewed, immutable snapshots (not a previously reconciled or test fixture
workbook), from a privileged and authorized read-only export process:

1. The full original **53-column** baseline invoice CSV, expected 14,374
   rows, original header positions untouched, along with an independently
   authenticated SHA256 of its exact file bytes.
2. The generated **18-column** Credit Note report CSV, along with its
   independently authenticated exact-file SHA256. The eighteenth column
   is the existing report contract label, not an invitation to modify it.
3. The three primary status CSV exports for the original 53-column report
   partition: unpaid, ok and error-value, plus balance-review if available.
   A private manifest for those exports must list exact paths and externally
   verified SHA256 digests. Do not assume an earlier report is today's data.
4. Separate approval/evidence that all files refer to the **same source
   snapshot**. The digest values must come from an independent approved
   provenance channel, rather than be self-certifying hashes computed only
   from the outputs under test.

Keep all CSVs and their manifests in a restricted operator environment.
Never push them to the public repository, GitHub Actions artifacts, chat,
an AWS public dashboard, an unsecured Google Drive folder, or debug logs.

## Running the two independent checks (offline)

Run from the reviewed repository checkout. No external Python dependencies,
database SDK, AWS permissions or network access are required:

    python tools/sbi_financial_report_parity.py \
      --original /private/approved_original_53.csv \
      --source-sha256 <independently_verified_64_hex_source_digest> \
      --report-manifest /private/primary_53_report_manifest.json

The private primary manifest shape:

    {
      "reports": {
        "unpaid": {"path": "/private/unpaid.csv", "sha256": "<digest>"},
        "ok": {"path": "/private/ok.csv", "sha256": "<digest>"},
        "error-value": {"path": "/private/error_value.csv", "sha256": "<digest>"},
        "balance-review": {"path": "/private/balance_review.csv", "sha256": "<digest>"}
      }
    }

Then check the Credit Note exact 17-field projection and 18th narration flag:

    python tools/sbi_credit_note_value_parity.py \
      --source-53 /private/approved_original_53.csv \
      --source-sha256 <independently_verified_64_hex_source_digest> \
      --credit-note-18 /private/credit_note_all_invoices.csv \
      --credit-note-sha256 <independently_verified_64_hex_credit_note_digest>

The tests are **independent** of production report builder functions. They
compare exact CSV cell text by approved position (including all monetary
cells) and preserve duplicate source rows. The intended CSV formula-injection
guard is applied to expected output values. They diagnose source/report
discrepancy counts by column, not by customer/invoice data. They never
calculate bank allocation, new TDS, or a new reconciliation status.

## Release interpretation

- SOURCE/REPORT MISMATCH or a bad file digest: REVIEW_REQUIRED.
- Exact Credit Note values with no duplicate/conflict exceptions:
  VALUE_PARITY_MATCH_SOURCE_APPROVAL_PENDING, **not** production approval.
- Duplicate/missing invoice groups and contradictory Credit Note evidence
  stay REVIEW_REQUIRED, even where source/report CSV cells match exactly.
- Primary 53-column status partition parity is not an independent bank
  payment allocation audit. It does not certify actual settlement decisions.
- Actual financial values and live connected reports remain unverified until
  these local private commands run on independently authenticated evidence.
- No traffic promotion, database writes, importer activation, dashboard edit
  or IAM grants follow automatically from either result.

Previously observed 9 duplicate/missing groups, 5 Credit Note conflicts,
and 4 GST source arithmetic exceptions are historical QA findings, not
freshly verified current counts. Do not auto-clear them.

## Independent review and signoff

Review exception counts against the original approved source. Preserve
immutable copies and a secure operator audit trail with reviewer identity,
timestamp, source/export file digests and signed disposition. No raw row
values belong in source control or automated CI. Financial release requires
a separate documented approval, including rollback and access-control tests.

## CI

.github/workflows/sbi-independent-report-values-qa.yml runs synthetic
unit tests for the existing primary partition checker and the new
Credit Note value checker. It has contents:read, no secrets, no GCP/AWS
calls, no finance payloads and no production deployment.
