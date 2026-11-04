# Stage 6D.8 — Firebase keyless identity approval intake (Lightsail-first)

**Current stage:** offline readiness review prepared. No certificates, trust anchor, Google WIF pool/provider, IAM grants, service-account permissions, real Firebase login, financial database connection, new AWS server or production cutover were performed.

## Confirmed by current Google documentation

- Google Cloud accepts X.509 client certificate chains from configured CA trust anchors and exchanges them over mTLS for short-lived credentials: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-x509-certificates
- Google documents `google.subject` mapping to `assertion.san.uri` and a provider condition `assertion.san.uri=="spiffe://example/path"`. The existing proposal's exact matching syntax is consistent with documented attributes. It is a *proposal*, not approval of the certificate authority's issuance security.
- Google requires a credential config plus separate certificate config that identifies certificate and **client private key** paths. No Google service-account private-key JSON is required, but client key protection remains mandatory.
- For API limitations, Google supports service-account impersonation; principal binding should target an exact subject rather than a whole WIF pool.
- Firebase session-cookie and revocation operations are distinct: `verify_session_cookie(..., check_revoked=True)` requires live user verification. `create_session_cookie` uses Firebase Identity Toolkit; least-privilege service-account access must be tested in isolated staging. Firebase user-account writes, `revoke_refresh_tokens` and admin-user provisioning remain disabled pending **separate** authorization: https://firebase.google.com/docs/auth/admin/manage-cookies and https://github.com/firebase/firebase-admin-python/blob/main/firebase_admin/_token_gen.py
- `google-auth>=2.39.0` is required. Owner's Stage 6D.5 result confirmed installed 2.62.1 and firebase-admin 7.7.0, **offline compatibility only**.

## Prerequisites missing before authorization

1. **Independent security sign-off:** a reviewer separate from the implementer must approve a certificate issuance threat model, host compromise response and account trust. This document is *not* that sign-off.
2. **CA custody:** define the authorized CA, restrict leaf issuance to the exact URI SAN, keep signing/root private key away from Lightsail, document CA key backup and disaster recovery. Do not use public CA default trust.
3. **Client private key:** approve secure generation and restricted non-root storage, encryption, rotation overlap, expiration alerting, immediate revocation/reissue procedure and how a compromised client key disables IAM credentials.
4. **Google permissions:** select dedicated staging service account, verify exact subject binding, document minimum Firebase Admin permissions and whether identity impersonation is needed. No financial roles or account-write privileges by default.
5. **Cost:** quantify certificate issuance, private key lifecycle and optional external/managed CA. No new EC2 or additional AWS server; do not enable a paid CA service without approval.
6. **Operational validation:** separate staged approvals for creating a disabled provider, adding exact IAM bindings, enabling only after review and testing one authorized read-only Firebase user lookup, then explicit real session tests. No wildcard provider IAM access.
7. **Rollback:** test disabling provider, removing exact IAM binding, invalidating compromised client identity, restoring prior Cloud Run functionality, preserving Lightsail public services.

## Combined code-only review

`python3 staging/aws_lightsail/stage6d8_review_gate.py --repo .`

This reads the earlier 6D.7 inert JSON proposal and reports per-control PASS/FAIL, seven named pending review items and final `BATCH_QA`. **A PASS means only that a still-inert proposal is consistent with governance; it never means IAM permission, certificate or Firebase login readiness.**

## Control decisions

- Approved platform: existing AWS Lightsail; zero EC2 additions.
- Existing AWS-federation WIF provider/pool remains user-reported disabled and unchanged.
- Proposed separate Google X.509 identity provider: not created.
- Independent review, owner cert custody / cost / IAM permission approvals: pending.
- Certificate/client key: not generated.
- Firebase Admin user read, real session login, logout, revocation: not tested.
- Financial database: not connected.
- Production deployment and cutover: blocked.

**NEXT_GATE=INDEPENDENT_SECURITY_REVIEW_AND_SPECIFIC_OWNER_APPROVAL**. No run commands that mutate cloud state may be issued solely because the user says "next".
