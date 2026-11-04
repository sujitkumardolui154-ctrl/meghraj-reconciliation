# Stage 6D.4 — Lightsail Firebase Admin identity decision record

**Decision status: BLOCKED — no authenticated provider approved, no production infrastructure change.**
Previous stage: Stage 6D.3 11/11 private HTTP tests passed on the existing Lightsail host; no credentials were exercised. A successful login page response is not successful Firebase Admin authentication.

## Non-negotiable Firebase feature parity

The currently deployed application **source** (not yet independently pinned to the Cloud Run image digest) requires:
- Browser login with Firebase Identity Toolkit + HTTPS permitted origin.
- Server-side `verify_id_token(check_revoked=True)` plus fresh `auth_time`, password-provider restriction and live disabled-user/custom-claims check.
- `create_session_cookie` and `verify_session_cookie(check_revoked=True)` plus `auth.get_user` on every protected request.
- `revoke_refresh_tokens` on logout, host-only Secure HttpOnly cookies and CSRF/Origin checks.
- Privileged admin user creation, setting custom claims and enable/disable operations. These must remain inaccessible in staging even if source code is packaged.
- `cloud_auth.get_backend_token` for Cloud Run backend, which is a separate credential/permission requirement. Do not infer dashboard login permission grants invoice or financial backend permission.

Firebase describes session-cookie revocation as requiring an extra request; public JWT signature verification by itself cannot replace revocation and disabled-user checks. Source: https://firebase.google.com/docs/auth/admin/manage-cookies

## Options evaluated

1. **Keep Firebase Admin on the existing Google Cloud backend, expose an additional narrowly scoped authenticated identity-verification interface to Lightsail.** Could avoid adding an AWS server, but the trust/authentication **from Lightsail to the backend remains unsolved**. Never expose a public unauthenticated validation endpoint or accept only a browser API key; needs a robust mutually authenticated transport, permission minimization, replay protection, rate limits, audit and independent threat review. **NOT APPROVED / NOT IMPLEMENTED**.
2. **Google WIF with AWS role credentials from an application-owned identity.** Google documents AWS identity federation using temporary AWS credentials from an instance profile; the current Lightsail metadata reports a service-managed AWS identity from a different account. The dedicated user-created IAM role currently has EC2 trust and is not directly available to the Lightsail process. No viable runtime identity has been proven on existing Lightsail. Do not enable the disabled Google WIF pool/provider or add an EC2 instance to solve it. **BLOCKED**. Source: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds
3. **Replace Firebase Admin session handling with locally verified Firebase JWTs.** NOT equivalent: revocation, user-disable and claims freshness checks, server session minting, logout invalidation and admin functions differ. Requires major redesign and review; **REJECT AS DROP-IN**.
4. **Static service account private key in Lightsail.** Avoids federation configuration at the cost of long-lived high-value secret risk. Owner's existing instructions prohibit service account private-key JSON; **NOT PERMITTED**.
5. **An EC2 instance for AWS instance profiles.** Technically provides a direct role but would be additional infrastructure or replace Lightsail; owner expressly locked **Lightsail-first**, so **PROPOSAL ONLY, NOT AUTHORIZED**.

## Current next steps (source/read-only)

- Stage 6D.4 combined audit: `python3 staging/aws_lightsail/stage6d4_identity_readiness.py --repo .`. It checks preserved code contracts and prints `BATCH_QA`; no SDK, cloud, secrets or financial data.
- Obtain an independently reviewed, Lightsail-compatible application-owned workload identity design, or an equivalently secure backend authentication interface, without setting up a new paid server or compromising revocation semantics.
- Separately estimate the operational costs and risk for each alternative and request specific authorization **only for the chosen trust / IAM / WIF changes**.
- Then validate one authorized real Firebase Admin user read and end-to-end login/revocation/role/logout under a private isolated environment (not a public endpoint); financial APIs remain blocked.

**Gate:** `REAL_FIREBASE_LOGIN=NOT_TESTED`; `AUTH_IDENTITY=BLOCKED`; `FINANCIAL_WRITE=NO`; `PRODUCTION_CUTOVER=BLOCKED`.
