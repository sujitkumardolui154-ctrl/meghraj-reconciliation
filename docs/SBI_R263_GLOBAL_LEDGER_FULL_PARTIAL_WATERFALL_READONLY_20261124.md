# SBI R26.3 — Synthetic global ledger and waterfall-last allocation rehearsal (24 Nov 2026)

**Development-only scope**. Not the authorized v2.51 / Matrix v2.39 settlement engine. Financial Apply remains LOCKED. No real bank data, finance writer, AWS/Cloud authorization or database writes.

## Owner instructions retained
- SOL development-reference master: owner-selected **27 October 2026** SBI_SOL_Branch_Master_FINAL.xlsx, historical verified SHA256 4a586592f0978ecd6bb3d4a8de0e2062476d2e414481252dd8da7b8b1f8ac388; **not imported into public CI**.
- Controlled full v2.51/v2.39 rebuild requested, but this is a staged component, **not** a full/released engine.
- Previously excluded **149** original-source rows stay quarantined in the private owner review register. **No restoration, deletion, remapping or financial source edit**.
- Preserve Invoice Details. original A:AH and J Invoice No / M SGST; PAYMNENT original A:L with I Credit; v2.18 model M:W and AI:AM remain unchanged in their separate writer.

## New R26.3 pure in-memory simulation
Module: scripts/ci/sbi_r263_global_allocation_shadow.py
Tests: tests/test_sbi_r263_global_allocation_shadow.py

All source records are restricted to SYN-MXP-### and SYN-PAY-###. The caller must supply two separate SHA-256 manifests of synthetic source/master fixture and ordered proposed edge/proof plan. The solver returns **only an ephemeral list of candidate shadow edges**, a cash-credit consumption view and an **invoice cash coverage gap (NOT legally/financially outstanding)**. Every outcome has financial_status=None, real_bank_payments_allocated=0, real_invoice_status_updates=0, real_database_writes=0, and financial_apply_locked=True.

The separate GlobalGate must precede waterfall proposals; earlier methods after the gate or waterfall before it are blocked. Repeated source IDs, repeated payment↔invoice edges, contradictory MXP reference, protected original K/S markers, invalid SOL or master, missing service-month/date evidence, and amounts exceeding **any** bank credit or invoice capacity cause atomic rejection of **every** candidate edge. No partial output survives a failed batch.

Implemented as **scoped synthetic rehearsal**, not real financial decisions:

1. Full exact-reference/unique 0–3% TDS hypothesis candidate; never sets financial OK.
2. Explicitly evidenced partial receipt proposals allowing two bank credits toward one invoice, while enforcing global credit/invoice conservation.
3. Waterfall proposals following the global gate, requiring **no contradictory explicit MXP** and a fictitious, pair-scoped SYN-PROOF-WATERFALL marker.
4. GST-later/component, SBISA SOL 1/blank invoice SOL, and cross-SOL relation **fictitious SYN-PROOF** requirements in synthetic tests. Such tokens are **NOT real owner approvals** and cannot enter production finance logic. Absence/mismatches reject.
5. Provisional DNM suggestions NEVER reserve cash, even in synthetic QA; alternate sources may not bypass contradictory narrations.
6. Duplicate source-ID and repeated-edge controls; equal amounts alone cannot classify an authorized payment duplicate. Financial statuses are deliberately absent.

**Important accounting distinction:** An exact bank credit of ₹1,160 for a ₹1,180 invoice may imply ₹20 withheld TDS, so cash-reservation subtraction leaves an artificial ₹20 **cash coverage gap**. This is **NOT** certified remaining receivable/outstanding. No withheld tax is booked as cash or financial settlement; full gross/TDS/credit-note ledger still requires independently approved source and accounting logic.

## What the combined R26.3 QA will establish
- New adversarial cases plus all previous R14–R26.2 isolated offline/synthetic tests and disposable PostgreSQL.
- No original SBI transactions, no approved real master contents, no real Firebase user credentials, no real AWS PostgreSQL connection, no external financial writes.
- Independent QA of full v2.51 implementation, true real-bank same-source parity, v2.18 real financial writer, row-level outstanding/GST/TDS accounting, credit notes, approved SBISA/parent-child aliases, duplicate final decisions, and staging production rollback **still unproven**. A passing test is not release.

**R26.3 evidence output:** code SHA, test counts, exact workflow run URL, owner issues/holds, no data writes, Finance Apply locked. Merge development PR only after passing exact-head checks. Production main unchanged.
