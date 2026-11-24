# SBI Financial Release — R21 Required Evidence & Owner Acceptance Register (24 November 2026 IST)

## Present determination
**Scope:** source/metadata inventory and development-only synthetic QA. **Financial Apply LOCKED**. Production `main` unchanged. A green R21 source-integrity/test workflow is *NOT* financial production authority.

The user requested to start collection and execution of remaining evidence before the 24 November handover. This entry distinguishes available verification from facts which require a fresh attachment, private host credential or an authorized signatory. Do NOT copy historical Source/Output files into the new financial production database.

## Verified against available sources

| Source checked | Verified observation | What it does **not** prove |
|---|---|---|
| Development branch `feature/sbi-payment-reconciliation-readiness-gate-20261120` | R14 and R15–R20 source safeguards and QA; verified exact commit `6e8e9e2cf3401bb2e88023b8c2c3b22420587425` before R21 branch creation | Full Master v2.51 / Matrix v2.39 allocation engine |
| GitHub recursive tree for same commit | 377 entries, no complete v2.51/v2.39 finance settlement runner located in inspected paths | Does not establish nonexistence in every private archive |
| Historical 28-Oct [repair blueprint](https://docs.google.com/document/d/1wrM3PtBI1MHzowVGdtTl8pl32xNk_SzLYBwbJDI8GIk/edit) | 13 gates (00–12), deterministic signed hash + global ledger + waterfall LAST + independent Finance signoff mandatory | Blueprint is a specification, not executable, signed source |
| Connected Drive/Library master inventory | Two Drive files named `SBI_SOL_Branch_Master_FINAL.xlsx`, and a Library reference of that name; historical hash `4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388` documented previously | No current owner designation, complete alias approval, source/signature proof or authorized fresh-execution master |
| Connected Drive project folder `SBI-Reconciliation-v2.51` | Historical `INVOICE MEGHRAJ EXPRESS SBI.xlsx` was archived on 20-Nov-2026, as source *reference* | Does **not** satisfy FFI-001: NEW user-submitted workbook for this execution or prove complete provider ledger |
| Recovered v2.22 scorer SHA `72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf` and earlier partial SHA `6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3` | Both known source hashes must be blocked from claiming full v2.51 | Old candidate/test source may never auto-settle or become signed final engine |
| [R20 combined QA run](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45355368414) | 206/206 development synthetic, PostgreSQL disposable + R14 offline source tests PASS, reviewed | No real bank account settlement, no real AWS read-only database access, no signed ID token accepted by real Flask runtime |

## Owner acceptance: actionable evidence, in dependency order

| Gate | Current state | Required closure package | Required provider / owner |
|---|---|---|---|
| FFI-001 fresh original workbook | **BLOCKED** | NEW original owner-submitted `PAYMNENT` + `Invoice Details.` workbook for this run. Immutable bytes and authoritative upload event + SHA256. No old reconciled model output substituted | Business owner / attached financial source |
| Approved SOL + aliases | **BLOCKED** | Select exactly one current master, authoritative approval date, SHA256, unsigned/duplicated/padded SOL review and alias signoff; keep original leading zeros as text | Owner/branch master approver |
| Complete v2.51/v2.39 executable | **BLOCKED** | Original runnable source or explicitly authorized full reconstruction; exact source-tree SHA, trusted author, implemented method map, independent denylist + QA | Engine builder + independent QA |
| Full Master allocation ledger | **BLOCKED** | Same-source complete proof on TDS HALF_UP 0/1/2/3%, same SOL/full & partial, service multi-month, MXP references, GST-later, DNM-01, SBISA SOL 1, approved parent/child, recency, duplicates and waterfall LAST with no over-allocation | Independent finance QA |
| Financial v2.18 writer and report parity | **BLOCKED** | Source A:L/A:AH immutable and correct M:W, AI:AM headers, but also real correct row statuses, amounts, 53-column report values and source-identical parity, one actual XLSX | Signed engine & independent writer QA |
| R14 real Firebase-to-Flask | **BLOCKED** | Authorized `sbi-r9-staging` Cloud Shell exact-result receipt for real signed Firebase ID token + actual Flask session, CSRF/cookie/status/Apply denial. **Offline 12/12 not a substitute** | Staging owner / IAM |
| Actual staging PostgreSQL | **BLOCKED** | Authorized real isolated staging identity + read-only snapshot/permissions, rollback proof and correct financial schema. **Disposable local CI PostgreSQL PASS is insufficient** | AWS/Postgres owner |
| Finance/security cutover approval | **BLOCKED** | Independently signed release matrix, scope, valid rollback, user-approved release decision. No self-asserted `approved: true` status and no automatic unlock | Finance officer + security + user |

## Owner's next safe actions (not runnable from public CI)

### R14 — authorized separate Firebase staging, no secrets in chat
The actual gated Python probe is already implemented at `scripts/ci/sbi_r14_real_app_session_readonly.py`. Use the exact [R14 owner-run instructions](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/blob/feature/sbi-payment-reconciliation-readiness-gate-20261120/docs/SBI_R14_REAL_APP_SESSION_READONLY_20261124.md) **only inside authorized Google Cloud Shell** with the approved staging QA service-account ADC and test claims. Do not paste API keys, tokens, passwords or credentials into GitHub or this chat. If missing ADC/approved claims: record `BLOCKED` without privilege escalation.

### Bank/SOL file intake
Upload the new original financial workbook in the current conversation or supply it through a specifically approved private source channel along with authentic source provenance; separately identify which of the master versions is latest officially approved. The engine must not automatically ingest the historical 20-Nov Drive archive as new evidence. Record private SHA256 and signed owner approval without exposing payment rows in public GitHub.

### AWS read-only staging proof
Needs authenticated owner-side AWS access. Run independently controlled **read-only** schema/role/snapshot/rollback checks on staging; do not reuse disposable CI host results and do not enable financial apply, execute a reconciliation or change AWS routing. A green script without confirmed target identity/permissions is not proof.

### Engine and Finance signoff
Locate and hash the *complete* v2.51 executable; if missing, the owner must authorize a separately reviewed rebuild. The recovered v2.22 scorer and partial candidate hashes are denied. Only then can real same-source independent golden-oracle parity, production writer output, and finance/security signoff start. Never infer approval from a number of synthetic passes.

## R21 test and artifacts
- `scripts/ci/sbi_r21_required_evidence_register.py` hashes only nine explicitly named safe development source/docs and builds a **read-only release status register**.
- `tests/test_sbi_r21_required_evidence_register.py` adds 26 forged approval, old source, and untrusted claim rejection tests.
- `.github/workflows/sbi-r21-required-evidence-combined.yml` re-runs **206 previous synthetic/disposable tests** plus these **26** tests (**232 total planned; exact GitHub Actions logs decide final result**), generates JSON evidence gate manifest and synthetic-only XLSX QA artifact.
- All real-release gates intentionally stay `BLOCKED_EXTERNAL_EVIDENCE`. The register cannot independently accept claims and will not lift Finance Apply.

**Final intended disposition:** Complete the verifiable development handover; do **not** report that actual v2.51 financial payment reconciliation is live or certified before all eight owner/provider evidence gates are independently satisfied.
