# SBI Stage 6D.6 — X.509 WIF security, cost and certificate lifecycle desk review

**Scope and evidence:** Owner's Lightsail result: Stage 6D.5 `batch_qa=PASS`; `google-auth=2.62.1`, `firebase-admin=7.7.0`, revocation/source contract PASS, `firebase_real_login=NOT_TESTED`, `x509_wif_provider=NOT_CONFIGURED`, `financial_database=NOT_CONNECTED`. This is a **design desk review, not independent security signoff or a production approval**.

**Owner deployment policy:** Continue on **existing Lightsail**; no EC2 or additional paid server, no Google or AWS IAM modifications, no certificate/private key creation, no financial data access or public application changes without separate explicit owner approval.

## Decision

**CONDITIONALLY FEASIBLE, NOT APPROVED FOR EXECUTION.** Google's X.509 Workload Identity Federation can exchange a certificate-backed, mTLS-authenticated workload identity for short-lived Google credentials on non-Google hosts. Python `google-auth` version 2.39.0+ supports the protocol, therefore 2.62.1 passes a **library requirement only**. The actual Firebase Admin credential flow, user/session revocation, service account impersonation, and integration under the container's non-root UID remain unverified.

Official documentation:
- X.509 WIF: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-x509-certificates
- Firebase session cookies/revocation: https://firebase.google.com/docs/auth/admin/manage-cookies
- Firebase Admin external credentials/signing: https://firebase.google.com/docs/auth/admin/create-custom-tokens
- Google IAM API pricing: https://cloud.google.com/iam/pricing
- Optional managed CA pricing: https://cloud.google.com/certificate-authority-service/pricing

## Risk controls required BEFORE any real credential setup

| Risk | Required control / acceptance criterion |
|---|---|
| Private key exposure | Treat X.509 **client private key as a highly sensitive secret**. No private key/CA key in Git, Docker build layers, image labels, shell history, chat, unencrypted backup or log. Dedicated non-root account access; encrypted-at-rest and secure restore/rotation plan; auditable host file permissions. Root CA signing key must not reside in the public-facing application container. |
| Scope escalation | Dedicated Google workload identity and narrowly scoped service account if impersonation is necessary. Separate Firebase Admin privilege from financial Firestore, Cloud Storage, imports, Cloud Run report APIs. Disable admin-user writes until approved. |
| Untrusted certificates | Use a private CA with limited issuance or exact certificate identity, unique immutable subject/SAN attributes, restrictive Google attribute conditions and exact principal IAM binding. Avoid wildcard grant to an entire pool or public-root-CA trust. |
| Certificate lifetime | Google's maximum supported *leaf* certificate lifetime is 390 days; propose short operational lifetime (e.g. 60–90 days) with rotation before expiration and alerting, subject to independent review. Rehearse overlap rollover, expiration, replacement and recovery. |
| Certificate compromise | Written emergency disable procedure for exact X.509 provider / IAM binding and certificate replacement. Verify revocation/invalidated-cert behavior empirically; do not assume certificate revocation list or OCSP behavior. For a single certificate, consider identity binding to fingerprint, with operator-controlled update on rotation. |
| Stolen access token | Short-lived access tokens; no caching to disk; review whether Context-Aware Access mTLS binding mitigates token replay in the chosen API path. Audit service-account impersonation scope. |
| Firebase Admin behavior | Private test one authorized user **read-only** followed separately by approved real login, revoked/expired sessions, disabled users, custom claims, logout, CSRF; prohibit admin account creation and financial API access until approval. |
| Service availability | Test external Google STS mTLS network availability and retry behavior only after approved setup; fail closed on auth/network errors, monitor certificate expiry, token exchange failures and rate limits. |
| Resource impact | Existing Lightsail has 909 MiB RAM and no swap. Avoid additional persistent processes or CA services without capacity assessment. Keep Stage 6D test containers disposable and isolated. |
| Security rollback | Preserve running Cloud Run and Lightsail services. Define disable IAM binding/provider, revoke/replace client identity, roll back app credentials/config, and independently validate restoration before cutover. |

## Costs (estimate, not actual billing)

- **No additional EC2, Lightsail instance or other AWS server** is inherently required by a direct X.509 WIF design.
- Google IAM API: official listed usage cost is **$0 for API use**. This is **not a promise that the complete end-to-end integration is free**. Firebase/Identity Platform quotas, network transfer, monitoring, storage, external PKI and any other services are separate.
- **Optional Google Certificate Authority Service:** currently published DevOps tier **$20 per CA/month + $0.30 per certificate** (first 50,000). The Enterprise tier is higher. **Do not activate paid CAS.**
- **Self-managed certificate authority:** can avoid a managed CA service subscription, but introduces ongoing certificate issuance, secure key custody, renewals, incident response and recovery obligations. Costs are operational and not zero; hosting/storage/network may still have charges.
- IAM API pricing: https://cloud.google.com/iam/pricing ; CA service pricing: https://cloud.google.com/certificate-authority-service/pricing . Verify prices again immediately before approval.

## Mandatory approval sequence (nothing executed)

1. Independent security review of the identity threat model and Firebase Admin credential flow, including least privilege and ability to revoke certificates.
2. Owner-specific approval **for certificate authority custody, issuance and client private-key handling** on existing Lightsail; no default permissions.
3. Owner-specific approval **for creation of a disabled X.509 Google WIF provider** and exact attribute conditions; do not modify the existing disabled AWS provider.
4. Only after inspection of configuration and independent review, explicit authorization to enable provider, narrowly scoped IAM access and a **read-only test user lookup**. Confirm Firebase Admin session minting and revocation separately; neither is implied by library compatibility.
5. No financial database or production traffic change without separate acceptance/release.

## Current gate

`DESK_REVIEW=COMPLETE`; `INDEPENDENT_SECURITY_SIGNOFF=PENDING`; `OWNER_CERTIFICATE_AND_IAM_APPROVAL=PENDING`; `GOOGLE_WIF_CHANGES=0`; `AWS_PAID_INFRASTRUCTURE=0`; `FIREBASE_REAL_LOGIN=NOT_TESTED`; `FINANCIAL_DATABASE=NOT_CONNECTED`; `PRODUCTION_DEPLOYMENT=BLOCKED`.

**Next recommended action:** Conduct review of private key custody, identity-binding and rollback plan; do not execute cert generation or Google IAM changes without separate owner approval.
