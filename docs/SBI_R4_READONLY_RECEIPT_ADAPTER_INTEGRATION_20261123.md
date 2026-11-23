# SBI R4 — Read-only Payment Evidence adapter, GitHub CI review

Source base: PR #120, commit 50a83330ff580e95494b4ce9ece5b998537b39a3.
This is an R4 consolidated implementation of the earlier R3 review design,
**not byte-for-byte identical** to the R3 package. It requires independent
Flask/Firebase-mock CI and owner code review before any merge or AWS action.

- Owner confirmed new-only **upload-receipt** cutoff 2026-11-23 00:00 IST.
- Three-column input stays Description | SOL ID | Credit Amount.
- Exact existing source-staging validation, owner/Firebase/CSRF, immutable
  receipt SHA, and saved/source summary checks run BEFORE the new adapter.
- The Flask preflight keeps existing 409 and 503 response semantics.
- Existing financial Apply POST endpoints remain disabled (HTTP 403).
- The adapter scans all accepted XLSX rows up to 10,000 (the separate upload
  service allows 30,000); larger files receive a 409 review hold, not a
  partially analyzed result.
- Quarantine configuration is private, normalized SOL keys for the three
  documented collision groups (3970,6884,6928); no private master XLSX,
  customer invoice data, real bank records, credentials or UTRs in GitHub.
- Upload SHA deduplication is not bank transaction deduplication; bank date,
  UTR, full Master v2.51, Matrix v2.39 and durable financial writer are not
  verified and MUST remain blocked.
- The 53-column A:BA and PAYMNENT A:L/M:W report contracts are unaffected:
  no Excel reconciliation writer is invoked by this adapter.
- This branch is development-only; CI uses mocked Firebase session and
  synthetic Excel. It is not bank-origin authentication or AWS live QA.

NO FINANCIAL DATA WRITE, NO AWS DEPLOY, NO PRODUCTION MERGE AUTHORIZED.
