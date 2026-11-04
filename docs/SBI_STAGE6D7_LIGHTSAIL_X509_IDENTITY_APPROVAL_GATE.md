# Stage 6D.7 — Approval-gated Lightsail identity configuration proposal

**Current status: SOURCE DESIGN PREPARED — independent security review and owner-specific authorization pending.**

**This record is not an IAM change request to execute immediately.** The user requested keeping the AWS Lightsail instance as the sole approved migration destination, no EC2 or other additional paid server, protected Google production, financial and account writes blocked, and combined offline testing.

## Evidence and purpose

- Stage 6D.3 on existing Lightsail: 11/11 anonymous/private HTTP security tests PASS; no external network, no real Firebase credentials.
- Stage 6D.4: Firebase Admin session source contracts PASS; no approved Lightsail Google credential.
- Stage 6D.5 user-observed local image: `google-auth=2.62.1`, `firebase-admin=7.7.0`; minimum `google-auth>=2.39.0` for Google X.509 WIF is met. This verifies **library version only**.
- Stage 6D.6: desk review recorded CA custody, lifecycle, costs, lease/renewal and token/revocation risks. **Not independent security signoff**.

Official Google documentation verifies a certificate-based external workload can use `GOOGLE_APPLICATION_CREDENTIALS` to refer to a non-secret external account *configuration* plus a **separate certificate config referencing a sensitive client private key**. Google recommends narrowly scoped principal binding and warns that a public CA trust anchor or broad pool-wide grant risks spoofing. Sources:
- https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-x509-certificates
- https://docs.cloud.google.com/iam/docs/workload-identity-federation
- https://firebase.google.com/docs/auth/admin/manage-cookies

## Proposed — NOT executed

A versioned read-only JSON plan is kept at `staging/aws_lightsail/stage6d7_x509_identity_plan.json`. Distinct dedicated pool and provider proposed solely for approval, **not created**:
- Suggested new staging pool: `sbi-lightsail-x509-stage`, provider: `sbi-lightsail-auth-x509` (X.509).
- Proposed subject mapping: `google.subject=assertion.san.uri`.
- Proposed exact subject: `spiffe://meghraj-reconciliation/stage/lightsail-auth`.
- Proposed CEL condition: `assertion.san.uri == 'spiffe://meghraj-reconciliation/stage/lightsail-auth'`.
- Proposed IAM principal: **only the matching workload subject**, never an entire pool or public-CA trust by default. The concrete numeric project path, target Google service account and permission bindings must undergo separate review; do not copy this example directly into live IAM.
- Client certificate validity proposal: 90 days (review rotation before expiration, overlap, recovery and revocation). Google's hard maximum supported leaf certificate lifetime is 390 days, **not** a suggestion to use 390 days.
- Signing/root CA key must be kept off the public Lightsail application host. The Lightsail **client private key** is a secret and must be protected, access limited to a single non-root workload, and never stored in Docker images, backups without encryption, logs, GitHub or ChatGPT.

**Do not create or enable a provider, generate certs/keys, alter Firebase users, modify service account roles or traffic until specific user authorization and independent review.** The existing disabled AWS provider/pool remain untouched.

## Security acceptance gates

1. Independent security reviewer signs off CA custody, exact identity/SAN and CA constraints, least privilege, threat-model of host compromise and token replay, on-disk key protection and emergency compromise playbook.
2. Determine who owns the separate certificate authority and how keys/certificates are generated, securely stored, renewed, rotated and revoked. If using managed CAS or external PKI, provide explicit recurring fees *before* approval. Self-managed CA has operational and secret-handling costs.
3. Resolve Firebase Admin permission profile: a dedicated service account and possibly impersonation may be necessary; confirm compatible token exchange, `auth.get_user` read, session-cookie creation, revocation check, logout and session-expiration semantics under staging. **Do not grant Firebase user-management privileges or financial roles without separate owner approval**. Some Admin API operations may require privileged scopes; independently assess this contradiction before any live test.
4. Validate `GOOGLE_API_CERTIFICATE_CONFIG` / `GOOGLE_APPLICATION_CREDENTIALS` handling under non-root Docker UID 65534 with **no credentials committed, copied into image, or exposed in logs**. No real Google STS call until approval.
5. Only after explicit review and owner-specific approval: create isolated **disabled** provider and carefully scoped bindings; separately authorize enabling it and the **read-only** Firebase Admin test. Stop and rollback on any uncertainty. This stage deliberately includes no executable cloud-change command.
6. Keep existing Cloud Run, Lightsail services and financial data untouched until separately approved parity and cutover.

## Cost and alternatives

- Existing Lightsail stays the approved host; plan proposes **zero new AWS servers**. No EC2.
- Google IAM API calls are priced at $0 on the official IAM pricing page; this does not mean Firebase, network, monitoring or certificate handling is free: https://cloud.google.com/iam/pricing
- **Google Certificate Authority Service remains unapproved.** Official DevOps price: $20 per CA/month + $0.30 per certificate for first 50k; do not enable without owner cost acceptance: https://cloud.google.com/certificate-authority-service/pricing
- Self-managed CA could avoid managed CA billing but brings signing-key custody, issuance, rotation, audit and incident-response obligations. **Total running cost is not yet quantified.**
- If certificate custody cannot be made secure on the current host, reassess other **Lightsail-compatible** approaches and present consequences; EC2 is explicitly not a default or authorized fallback.

## Combined offline review

```bash
python3 staging/aws_lightsail/stage6d7_validate_identity_plan.py --repo .
```
This performs one offline bounded-plan review with per-check results and prints `BATCH_QA=PASS` only when the **proposal's no-change controls** are intact. It is not an external penetration test, identity login, approval or deployment validation.

**Even after a PASS:**
`AUTH_IDENTITY=NOT_ESTABLISHED`
`INDEPENDENT_SECURITY_SIGNOFF=PENDING`
`OWNER_CERTIFICATE_APPROVAL=PENDING`
`OWNER_IAM_APPROVAL=PENDING`
`REAL_FIREBASE_LOGIN=NOT_TESTED`
`FINANCIAL_DATABASE=NOT_CONNECTED`
`PRODUCTION_CUTOVER=BLOCKED`

**Next gate:** Determine whether an external independent reviewer accepts the certificate-custody and identity isolation plan, obtain specific owner approval to configure a disabled provider and cert lifecycle only when risks/costs are adequately addressed. Generic 'next' or 'start' does not constitute such authorization.
