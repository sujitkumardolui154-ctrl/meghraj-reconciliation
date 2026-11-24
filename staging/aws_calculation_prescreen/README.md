# R29 Isolated AWS/localhost Calculation Candidate Screening — SOURCE ONLY

R29 connects the **R28 owner-approved row-level exclusion policy** to a
separate Flask/Gunicorn candidate-preview gateway. This is **not** the
complete Master v2.51/Matrix v2.39 allocation engine. It is a *pre-screened
candidate review* contract. The R29 API does **not** independently apply
financial matching rules; the caller must not pretend otherwise.

## Endpoint surface

- `GET /healthz` — uncredentialed minimal status; explicitly reports
  `FULL_V251_V239_NOT_CONNECTED`.
- `GET /readyz` — 503 until `SBI_CALC_PREVIEW_ENABLED=true`,
  `SBI_FINANCIAL_APPLY=LOCKED`, and credentials are configured; 200 then
  **only for pre-screened development review**.
- `POST /api/candidate-screen` — authenticated private JSON request,
  bounded 512 KiB, max 1,000 pre-screened rows and 4,000 candidate edges.
  Returns a count/row-reference-only partition: eligible, excluded, held,
  candidate edges, rejected edges and reason codes; no source client names,
  financial amounts, bank UTRs, passwords or original file bytes in response.
- All other routes and methods 403. No status writer or DB client is copied.

**Owner decision:** a standalone Finance certification process is **not**
required to deploy a calculation/report feature. This is separate from
releasing authentic payment settlements. This build has
`financial_apply=LOCKED`, no actual financial posting, no Column M updates.

## Private localhost build procedure (NOT executed by GitHub Actions)

For explicit operator-approved, isolated, non-production staging only:

```bash
# Run from repository root after independently reviewing exact source SHA
export SBI_CALC_PREVIEW_ENABLED=true
export SBI_CALC_PREVIEW_USERNAME='<your private staging-only username>'
export SBI_CALC_PREVIEW_PASSWORD='<unique strong staging-only secret, >=24 chars>'
docker compose -f staging/aws_calculation_prescreen/compose.local.yml up --build -d
# Health/ready route is localhost-only; financial Apply remains locked
curl --fail http://127.0.0.1:18088/healthz
curl --fail http://127.0.0.1:18088/readyz
```

Use PRIVATE TLS ingress for any remote access. Do not paste credentials,
bank amounts, actual customer rows, workbook contents or UTRs into GitHub
issues, PRs, Actions or server logs. Do not expose port 18088 publicly.
Actual AWS deployment requires an authorized host operator; this PR cannot
access the live AWS terminal or validate IAM/restore behavior.

## Request format (synthetic only)

```json
{
  "mode": "PRE_SCREENED_CANDIDATE_REVIEW_ONLY",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "records": [
    {"role": "INVOICE", "source_row": 2, "source_identity": "SYN-MXP1", "result": "PASS", "reasons": []},
    {"role": "PAYMENT", "source_row": 2, "source_identity": "SYN-EVENT1", "result": "HOLD", "reasons": ["BANK_UTR_REVIEW"]}
  ],
  "matches": [
    {"invoice_row": 2, "payment_row": 2, "result": "PASS", "reasons": []}
  ]
}
```

`source_sha256` and all PASS/EXCLUDE/HOLD decisions are **caller-provided,
unverified**. Never label output as independently verified reconciliation.
A HOLD row will not generate an eligible candidate. No bank cash is reserved.

## Still required to deliver the user's requested full working engine

1. Complete runnable Master v2.51 / Matrix v2.39 rule implementation,
   including real source Excel parsing and approved SOL identity resolution.
2. Original current-run FFI-001 intake provenance and read-only protected
   `PAYMNENT` A–L / `Invoice Details.` S source handling.
3. Bank evidence, exact MXP, monthly periods, GST/TDS, full/partial, DNM,
   SBISA, cross-SOL, duplicate and waterfall method coverage.
4. Real v2.18 report writer parity and private authenticated runtime QA.
5. Actual AWS staging host access and technical release checks; **no separate
   Finance certificate needed for calculation/report deployment**.

A green GitHub test means the isolated preview is valid development software,
not that full reconciliation is running on AWS.
