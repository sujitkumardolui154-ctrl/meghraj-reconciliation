# SBI DB-R31.6 — private Firebase-authenticated staging candidate

**Release boundary:** this is a new **private staging** build of the existing AWS Firebase login and fixed-header payment upload application. It is NOT a replacement for the live Caddy preview and never connects to the authoritative central `sbi_reconciliation_main`.

## Source of truth and money display

- Original private receipt and immutable XLSX are retained by the established `payment_evidence_upload.py` route, Firebase session middleware and same-origin `X-DIL-CSRF` check.
- Authorized sync of one previously uploaded receipt: `POST /api/r31-private-qa/receipts/<private_receipt_id>/sync`. The owner is read from `g.dil_user.uid`, never from a form, URL parameter or request JSON. The receipt owner, original SHA, filename, workbook parser summary and exact original source row numbers are reverified. Readable source-credit events are stored only in `sbi_r31_owner_qa_20261125` with no invoice matching, UTR or bank date inference. Unknown SOL is held for official SHA-pinned master review.
- `GET /api/r31-private-qa/status`, `.../sol-report`, `.../payment-details`, and the equivalent `.csv` URLs require valid Firebase session. The database role is `sbi_r31_ownerqa_report`, with read-only transactions and owner-parameterized source queries. Production and QA source identities must remain separate.
- Internal PostgreSQL money remains integer **paise**, while every user-facing R31.6 report displays **rupees** and CSV amount fields contain numeric rupee values. Example: `credit_paise=11800` -> JSON `credit_received_rupees: "118.00"`, display `₹118.00`, CSV `118.00`. This is not ₹11,800. Original SOL `001505` remains text.
- No consumer endpoint can report `MATCHED` or `UNMATCHED_AFTER_RUN`; the correct source-only state is `NOT_CALCULATED`.

## Deployment scope

A new image is built from `Dockerfile.r31_private_staging` with the original Firebase login and accepted upload source plus isolated QA adapter code and psycopg client. The new app code registers the QA Blueprint **only** when `SBI_R31_PRIVATE_STAGING_ENABLED=isolated-ownerqa-firebase-csrf-v1`; the public live image keeps this unset.

`r31_stage_private_qa.sh` is **stage-only**, SHA-pinned and root-invoked. It checks QA database/owner index state, Caddy network and existing running app, private Firebase service account and source QA DB role files; it starts `sbi-r31-auth-private-qa` as nonroot in read-only Docker with no host published port, without writing Caddy routes. The applicant's real login/session has **not** yet been used against this candidate. It only tests anonymous denial and health; do not equate this with authenticated parity.

The container receives a **new empty private receipt folder** `/var/lib/sbi-r31-auth-qa/evidence`, not the live evidence folder. It can stage only its own new test XLSX receipts, not read real production receipts or private bank files.

## Operator steps

From already checked out project repository:

```bash
BRANCH=feature/sbi-r31-authenticated-staging-20261125
git fetch -q origin "$BRANCH"
git checkout --detach FETCH_HEAD
SHA="$(git rev-parse HEAD)"
bash -n staging/aws_login_v150/r31_stage_private_qa.sh
sudo bash staging/aws_login_v150/r31_stage_private_qa.sh "$SHA"
```

Do not run `activate`, change Caddy routes, give the browser a public Caddy endpoint, connect to production PostgreSQL, or grant source financial writes. Keep previous QA and current preview unchanged. If runtime check returns `STOP=`, report the exact error without uploading credentials.

## Remaining mandatory acceptance

1. Verify a real owner Firebase account with valid dashboard claim, signed session and correct same-origin `__Host-` CSRF cookies against a **privately accessible** staging origin; verify rejected unauthorized, wrong-owner, revoked, expired and cross-origin requests. Never share Firebase session cookies or password.
2. Upload one *synthetic* Excel file via the existing authenticated upload route in that private staging context; sync receipt and compare QA PostgreSQL source and versioned status, SOL summary and details/CSV. Verify both owner isolation and no duplicate replay with actual sessions.
3. Verify SOL branch master SHA and parser behavior for numeric/formatted Excel credit inputs. This QA adapter intentionally refuses source cases it cannot reproduce exactly; do not silently normalize unsupported inputs.
4. Implement and verify independent production tenant-level database authorization/roles/RLS and a separate approved central migration before any production source writes.

**Current status before AWS execution:** `DB_R31_RELEASE_STATUS=PRIVATE_AUTH_QA_STAGING_CANDIDATE_ONLY`. Code and local CI != actual signed-in Firebase QA. No allocation engine or financial invoice writer is connected.
