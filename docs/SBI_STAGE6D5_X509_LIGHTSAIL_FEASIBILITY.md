# Stage 6D.5 — Google X.509 Workload Identity Federation feasibility (Lightsail only)

**Status:** Offline compatibility review. X.509 provider / trust and account permissions NOT configured. Real Firebase Admin authentication NOT tested or approved. No EC2, IAM change or financial access.

Stage 6D.4 Lightsail output confirmed `source_contract=PASS`, but `firebase_admin_keyless_runtime_identity=BLOCKED_NOT_ESTABLISHED`. Source tests do not authorize live credentials.

## Candidate: X.509 certificate-based Google Workload Identity Federation
Google supports mTLS X.509 federation for external workloads using a CA trust anchor and a client certificate, enabling short-lived Google Cloud access tokens without storing a **Google service-account private-key JSON**. `google-auth>=2.39.0` is required for Python certificate federation. This is potentially suitable for the **existing** Lightsail instance without an AWS EC2 instance profile.

Official documentation: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-x509-certificates

**Important qualification:** Certificate-based federation is **not free of secret material**. It uses a certificate-associated private key with secure storage, issuance, renewal, revocation, least-privilege binding, account access approval and possible CA/certificate operating costs. Do not create certificates, turn on providers, grant IAM, or install private keys before independent review and owner approval. Reuse no generic public TLS server key for client identity.

For Firebase Admin, ADC external account credentials may require service-account impersonation and carefully scoped permissions to access Identity Toolkit/Admin APIs. Before any configuration, validate actual library/API support and minimum permissions in isolated staging. No real-user tokens or billing data.

## Other candidates
1. AWS IAM Roles Anywhere plus temporary role credentials and AWS-to-Google WIF: avoids long-lived AWS API keys but requires workload X.509 private key, CA trust, IAM role/profile, certificate rotation and potentially AWS operating charges. More components than direct Google X.509 federation. https://docs.aws.amazon.com/rolesanywhere/latest/userguide/introduction.html
2. Existing Google backend acting as authenticated verifier: requires trusted Lightsail-to-Google transport and revocation-aware API; additional architecture/security review and likely extra operational burden.
3. EC2 instance profile: technically simple but explicitly **not approved** as it changes the target/cost.
4. Static Google service-account JSON: **not permitted**. Offline JWT-only verification: **not equivalent** to existing revocation-checked Firebase Admin sessions.

## One combined read-only version/contract preflight

The stage's source script `staging/aws_lightsail/stage6d5_x509_feasibility.py` runs inside the **already built** image as a temporary network-none container, reads package versions and non-secret application source contracts only. Do not supply credential mounts, client certificates or Google IAM/SDK tokens. Source script and image can be pinned for repeatability.

Example command is provided separately to owner. It exits 0 only for offline library compatibility, **not** live authentication readiness.

**Next gate:** Independent certificate lifecycle, least-privilege IAM, Google provider policy, Firebase Admin ADC behavior, authorization and cost review. Until approval: `AUTH_RUNTIME=BLOCKED`, `FINANCIAL_DATA=NOT_CONNECTED`, `PRODUCTION_CUTOVER=BLOCKED`.
