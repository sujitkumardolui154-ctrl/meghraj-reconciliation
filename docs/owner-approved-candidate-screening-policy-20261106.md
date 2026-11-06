# Owner-approved SBI candidate screening policy — 2026-11-06

**Authority:** Application/account owner instruction and reviewed 11,841-record private screening file.  
**Status:** `OWNER_APPROVED_BUSINESS_RULE_POLICY`. NOT a financial release or blanket bank-to-invoice payment settlement.  
**Change:** New business-rule addendum. Historical approved rulebook, header contracts and source financial records remain intact.

## Owner authorization
The account holder confirms their authority to approve business-rule preferences and application-level review decisions. No redundant external person needs to sign these **business-rule changes** in this owner-controlled application. This does **not** waive evidence required to prove transaction identity, payment amount, uniqueness, factual bank narration, financial conservation, or release integrity. External legal/regulatory requirements, if any, are not replaced by this owner instruction.

## Three owner-approved conditional methods

| Rule | Original candidate-screen category | Private reviewed count | Owner-approved method |
|---|---|---:|---|
| OWNER-RULE-01 | SINGLE_POTENTIAL_SAME_SOL_TDS | 2,808 | Use same-SOL link and narration invoice references, accepting tokenized `MXP`, `M X P`, mixed case, and numeric suffix variants; consider explicit invoice date and/or full service month/period against the source invoice when the bank amount is not an exact amount match. Preserve contradicting reference evidence and existing allocations. |
| OWNER-RULE-02 | MULTIPLE_POTENTIAL_INVOICES | 451 | Examine same-SOL nearest approved TDS/amount scenarios, invoice identity/period and supported unknown deductions (e.g., claimed late delivery/loss). Preserve residual, method, source evidence; record `UNKNOWN_DEDUCTION` where reason or value is unresolved. Do not silently break ties between invoices or write off deductions. |
| OWNER-RULE-03 | NO_NEAR_EXACT_SAME_SOL_CANDIDATE | 8,582 | Extend review beyond a single gross/TDS amount to authorized consolidated multi-invoice payment, taxable/base payment excluding GST, later GST remittance, and possible unknown deduction. Quantify combined invoice and GST components; ensure original bank credit conservation and no duplicate claim. |

The private uploaded review used a single category-level instruction repeated for each bank row; no record-specific payment decision was supplied.

## Required data semantics

- The original **35 invoice evidence columns** are protected. In the approved **53-column projection**, the 18 model/audit fields occupy their approved positional columns (two inserted after original H, sixteen after original source columns); never assume report columns 1–35 are all original fields.
- Preserve `PAYMNENT` original columns A:L. **Bank credit input is column I alone.** Original invoice payment/eligibility markers (including S in original 35-column layout) are immutable.
- SOL IDs and invoice numbers remain strings; preserve leading zeros. Owner's reviewed Excel export reinterpreted some date and numeric fields, including three SOL cells; the canonical bank-row source values are authoritative.
- Preserve the previous approved allocation ledger. No prior `OK`, provisional authorization or outstanding balance changes merely because a new policy was accepted.
- Future generated model statuses retain exactly the three approved values: `OK`, `SUSPENSE`, `Duplicate Payment`; write details into model remarks or the independent Error Report.
- Narration matching is corroborating evidence; date-only or month-only, unsupported invoice reference, near-exact amount, or unidentified deduction **alone** is not proof that a particular invoice is paid.
- Multiple distinct eligible invoices, competing bank credits, missing original invoice eligibility, conflicting MXP reference, or impossible reconciliation remain review/ `SUSPENSE` until resolved under the full rulebook.
- `UNKNOWN_DEDUCTION` denotes a proposed explanation, not a verified write-off, fee, bank regulation or tax adjustment. Without documentary amount reconciliation, keep a residual and a review flag.
- Only transaction-specific, verified evidence may justify a new model `OK` recommendation. Independent technical QA is not an additional **owner/signature** requirement; it is a falsifiable data-integrity check.
- Financial database writes, PR mergers, routing changes and production deployment remain subject to separate approval/technical release gates; this policy approval is not that authorization.

## Evidence audit
- 11,841 positive bank credits; 3 reviewed category descriptions; owner policy accepted for all bank records.
- The uploaded file explicitly retains `New Allocation Approved=NO` for all 11,841 rows and `Provisional Model Decision=UNRESOLVED_REVIEW_REQUIRED`. Therefore `NEW_PAYMENT_ALLOCATIONS_AUTHORIZED_BY_THIS_REVIEW=0`.
- User's private reviewed file, canonical CSV and merged approved-rule report are in the owner's private ChatGPT conversation attachments, **not** uploaded to public GitHub.
- No additional finance staff sign-off required to *record these three rules*; independent bank-source and invoice checks still required for factual settlement labels.

## Implementation/QA handover
1. Update the **staging** matcher to recognize the three approved methodologies and all relevant narration, service-period and GST-later scenarios.
2. Build adversarial regressions for same-SOL ambiguity, invoice/date mismatches, duplicate payment competition, GST withheld versus received later, mixed-case/spaced MXP tokens, and wrong-amount unknown deductions.
3. Create a private read-only ledger with invoice row, bank row, payment credit, TDS hypothesis, component GST status, original evidence, deduction residual, all competing invoices, prior allocation reference, and reason for `OK` versus `SUSPENSE`.
4. Compare source hashes and do not silently import Excel-reformatted dates, monetary cells or SOL IDs.
5. Keep application production/financial release `BLOCKED` pending actual deployment, value parity, auth, backup and recovery proof.

**Approval summary:** `OWNER_RULE_POLICY=APPROVED`, `ROW_LEVEL_PAYMENT_ALLOCATION=NOT_VERIFIED`, `FINANCIAL_WRITES=0`, `PRODUCTION_DEPLOYMENT=BLOCKED`.
