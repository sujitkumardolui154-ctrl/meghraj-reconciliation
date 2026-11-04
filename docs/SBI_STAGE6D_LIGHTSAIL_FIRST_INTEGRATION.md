# Stage 6D — Lightsail-first full dashboard integration review

**Decision: continue source preparation on existing Lightsail; DO NOT purchase EC2 yet.**

## Evidence
- Existing Lightsail: Docker 29.1.3; 909 MiB RAM, ~375 MiB available during recovery, no swap; existing stage UI/Caddy/private preview must remain untouched.
- `sbi-full-dashboard-stage6c:191de0641529` built on Lightsail, but `Dockerfile.stage6b` explicitly blocks startup. Synthetic login redirects, cookies, denied API checks passed. Neither deployed live Firebase login nor finance feature parity.
- AWS STS on Lightsail returned assumed role `AmazonLightsailInstanceRole` from `731738810135` while customer's AWS account is `146415808408`. Not an application-owned credential. No role reuse for Google WIF.
- Dedicated role `SBI-Firebase-WIF-Stage` has 0 AWS resource policies, EC2 trust and instance profile but is NOT attached to Lightsail.
- Google WIF pool/provider are user-reported disabled; no Firebase Admin verification conducted.
- Calculator estimate is **$19.09 USD per month** for Mumbai t3.small compute + 30 GB gp3 alone; networking, taxes, data transfer, backups and existing Lightsail costs excluded. No EC2 created.

## Important separation: browser login and privileged Firebase Admin

1. The browser `dashboard_source/login.js` uses Firebase Identity Toolkit HTTPS password sign-in. This can be hosted on Lightsail with HTTPS, authorized Firebase domain and a public web API key. Browser-only sign-in is NOT the same as server session verification.
2. The existing `dashboard_sessions.py` uses Firebase Admin to verify ID tokens and revoked session cookies, retrieve user custom claims, issue session cookies and revoke refresh tokens. `dashboard_users.py` creates users. These privileged operations require a trusted Google credential with appropriately scoped permissions. A mere Firebase web API key must NEVER authorize privileged operations.
3. `cloud_auth.py` obtains Google Cloud Run ID tokens using Google credentials. Report backend, monitoring, credit note Cloud Storage and Google Firestore integrations need separate identity and permission gates. Do not assume browser login grants backend access.
4. An alternative Lightsail session architecture using locally verified Firebase-issued JWTs with Google's published signing keys would require explicit session, revocation, user-disabled and claims-freshness design; it is NOT drop-in equivalent to `firebase_admin.verify_session_cookie(check_revoked=True)`. Avoid enabling it without independent threat review, logout and rotation tests.
5. EC2 with a dedicated instance profile is a straightforward future option if full app with Google identity cannot be achieved safely on Lightsail. No hosting migration decision until cost/security review.

## Engineering gates
- Keep the Lightsail public pipeline preview and Cloud Run dashboard intact.
- Keep full dashboard Stage 6 image non-runnable and backend/report/import API paths fail-closed.
- Audit current deployed Google Cloud revision, exact backend privilege flows and isolated data requirements.
- Design/approve a keyless application-controlled Google credential route on Lightsail OR select EC2 as final single host after financial approval.
- Only then enable a controlled private HTTPS login endpoint and test active/revoked/expired sessions, roles, CSRF, logout and no finance access.
- No second server provisioned, no WIF enablement, no financial write, no user account changes.

Run read-only source inspection from a pinned GitHub worktree:
```bash
python3 staging/aws_lightsail/stage6d_lightsail_integration_audit.py --repo .
```
A successful audit is an inventory result, **NOT** live authentication or migration approval.

**Next release gate:** `BLOCKED_PENDING_KEYLESS_IDENTITY_DESIGN_PRIVATE_LOGIN_AND_PARITY`.
