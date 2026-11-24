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


## R30 — Safe AWS staging resume (source-only until executed on AWS)

**No standalone Finance certificate is required for the calculation/report application deployment.** This is an explicit OWNER policy, not permission to fabricate payment matches or activate the database settlement writer. The R29 preview is still not the complete Master v2.51 / Matrix v2.39 engine.

The R30 host runner `staging/aws_calculation_prescreen/host_stage.sh` controls the isolated private **127.0.0.1:18088** container and no other endpoint. It binds a pinned 40-character checked-out Git SHA to the Docker image, performs preflight, builds the same pinned image, runs a no-network and readonly smoke test, starts only the separately namespaced Compose service, verifies HTTP 200 health and readiness, 401 unauthenticated preview, 403 financial write routes, and rolls back this isolated service on a failed health gate. It never alters existing public preview, Caddy, port 80/443 or database.

**Operator preparation is still needed on the real AWS staging host** (GitHub Actions only runs a disposable local test). Use a separate checked-out repository directory containing the reviewed branch commit; do not execute this script against the live website repository checkout. The AWS administrator must verify the exact SHA and supply the restricted local Docker privilege.

An administrator must create private staging-only `/etc/sbi-calc-prescreen/stage.env` (root-owned, 0600, not a symlink; parent not writable by others). Exactly three literal lines (not sourceable shell commands):

```dotenv
SBI_CALC_PREVIEW_ENABLED=true
SBI_CALC_PREVIEW_USERNAME=REPLACE_WITH_UNIQUE_STAGING_USERNAME
SBI_CALC_PREVIEW_PASSWORD=REPLACE_WITH_UNIQUE_RANDOM_STAGING_PASSWORD_24PLUS
```

Use your own generated 24–128-character random password comprising alphanumerics/dot/underscore/hyphen, never the example or existing SBI preview login password. Do **not** paste secrets here or into GitHub and do not include them in GitHub Actions output.

From the dedicated **reviewed SHA checkout** on the host:

```bash
# PREVIEW: read-only checks, no database or container changes; no secret needed
bash staging/aws_calculation_prescreen/host_stage.sh preflight "$(git rev-parse HEAD)"

# STAGE: operator explicitly invokes only isolated localhost deployment.
sudo env SBI_R30_STAGE_SCOPE=PRIVATE_LOOPBACK_ONLY \
  SBI_R30_SECRET_FILE=/etc/sbi-calc-prescreen/stage.env \
  bash staging/aws_calculation_prescreen/host_stage.sh stage "$(git rev-parse HEAD)"

# Read-only status of that exact checkout/host, no public route changes.
bash staging/aws_calculation_prescreen/host_stage.sh status "$(git rev-parse HEAD)"
```

A positive R30 status means only **pre-screened** PASS/HOLD/EXCLUDE gateway readiness; the HTTP health response explicitly says `full_v251_v239_engine_connected=false`. The app does not accept raw Excel uploads, does not calculate bank allocations, and cannot write PAYMNENT Column M or database financial results.

### Incomplete work to actual full operational deployment

1. Integrate the complete approved v2.51/v2.39 rule runner and user-uploaded real original workbook without inserting confidential data into public GitHub. Resolve official SOL master authority.
2. Connect the existing authenticated dashboard's **Payment Reconciliation** button to a private full calculation endpoint only after genuine method eligibility is available; **no auto-reconciliation on file intake** until the user confirms that mode.
3. Implement source-preserving v2.18 output values and real same-source method parity, then verify the actual AWS staging host using authorized commands and distinct staging credentials.
4. Only after those checks promote the calculation/report feature to user-facing AWS routing. Do not promote candidate-only preview as real reconciliation.

This runner is **not** installed or deployed to AWS by creating this PR, and even a green remote GitHub Action is a disposable synthetic Docker test, not a live AWS host receipt.
