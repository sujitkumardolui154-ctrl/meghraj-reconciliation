# Stage 6C-7 — AWS identity and full-host migration decision

Status: **ARCHITECTURE REVIEW ONLY — DO NOT PROVISION OR DEPLOY**

## Confirmed user-side evidence (4 Nov 2026)

- AWS Lightsail host runs the protected pipeline preview, while full dashboard source Docker image `sbi-full-dashboard-stage6c:191de0641529` was built as package-only with non-runnable entrypoint. Synthetic Firebase/session/CSRF tests passed, not live user authentication.
- User AWS console account: `146415808408`.
- On Lightsail, `aws sts get-caller-identity` returned account `731738810135` and assumed role `AmazonLightsailInstanceRole`, not controlled AWS application role. **Never authorize it for Google WIF.**
- User-created role `arn:aws:iam::146415808408:role/SBI-Firebase-WIF-Stage`, EC2 trust principal, zero attached policies, one-hour max session, EC2 instance profile exists; no EC2 has been attached to it.
- Google WIF pool `sbi-aws-migration-pool`, provider `sbi-aws-lightsail`: user screenshots showed pool disabled and provider disabled; configured role-only CEL condition `assertion.arn.startsWith('arn:aws:sts::146415808408:assumed-role/SBI-Firebase-WIF-Stage/')`, final save not independently re-verified. Separate existing `sbi-github-pool` untouched.
- Firebase user-read roles, WIF service account delegation, keyless credential config, live browser login and 53-column finance parity are all **NOT VERIFIED**.

## Distinguish Firebase login components

1. Browser sign-in uses Firebase web configuration and Identity Toolkit over HTTPS. Firebase browser SDK API keys are configuration identifiers, not service-account credentials. Authorized hosting domains and CSRF/cookie behavior need checks.
2. Server-side `firebase_admin.auth.verify_id_token`, `verify_session_cookie(check_revoked=True)`, `get_user`, `create_session_cookie`, `revoke_refresh_tokens`, and user-management endpoints need Google identity and specific permissions. AWS WIF is one possible keyless method; it is not automatically satisfied by browser Firebase sign-in.
3. No `GOOGLE_APPLICATION_CREDENTIALS` pointing to Google service-account private keys. Do not use the Lightsail-provided AWS `AmazonLightsailInstanceRole` from a different account.

## Architecture options

| Architecture | Merits | Costs/risks | Decision |
|---|---|---|---|
| Existing Lightsail + auxiliary EC2 token identity gateway | Retains existing preview/hosting | Adds a permanent second compute surface, authentication and routing complexity, egress and monitoring; gateway must not expose generalized token issue endpoint | Not recommended as default |
| EC2 host for full SBI application with `SBI-Firebase-WIF-Stage` instance profile | Native temporary identity on same application host; simpler keyless GCP federation; can move full app and keep Lightsail rollback | New AWS compute/EBS/IP/data-transfer charges; entire app still must pass authenticated functional parity and disaster recovery | **Preferred candidate for cost/feasibility study**, not automatic deployment |
| Lightsail + independent identity broker | Can keep current hosting | Broker trust design, identity assertion delegation and revocation complexity; avoid keys or broad impersonation | Review only if EC2 migration is not viable |

## Price and capacity evaluation

- Current Lightsail user console showed **909 MiB RAM**, no swap, with high existing RAM utilization. Full dashboard/image migration may need >1 GiB, especially with Caddy and preview; benchmark memory/cpu before sizing.
- EC2 `t3.small` offers 2 vCPU / 2 GiB RAM. Regional Mumbai Linux on-demand rates observed in third-party public pricing were about **$0.0224/hour (~$16.35 per 730 hours)**, **excluding EBS, public IPv4, transfer, taxes and potential CPU credits**. Verify live price in AWS calculator for the chosen plan; values are indicative only.
- EC2 `t3.micro` has 1 GiB RAM and may reproduce memory pressure; do not choose merely because of smaller price.
- Two-server hosting means Lightsail bill **plus** EC2 and any associated services; one-server EC2 migration only reduces total cost after cutover and Lightsail decommission (not yet authorized).
- References: https://aws.amazon.com/ec2/pricing/on-demand/ , https://docs.aws.amazon.com/lightsail/latest/userguide/security_iam_service-with-iam.html , https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds .

## Stage-gate and next no-write actions

1. Obtain cost estimate and confirm planned instance shape/region, AMI, EBS size, IPv4 address, outbound transfer and backup.
2. Verify exact deployed Cloud Run revision and original dashboard feature parity requirements; source inventory is not deployed-state proof.
3. Prepare a **private EC2 candidate only after cost approval**, with the dedicated role via instance profile; no broad AWS policies and no open public financial API routes.
4. Independently verify the disabled WIF provider's role condition, scope Google service-account impersonation to the approved role principal only, and grant minimal Firebase user-read permissions to that service account.
5. Test one read-only Firebase user lookup using keyless WIF; then explicit real session/role/CSRF/expiry tests in private staging.
6. Preserve live Lightsail and Google Cloud services, then execute end-to-end functional parity and rollback before any cutover. Financial writes remain 0.

Release: `BLOCKED_PENDING_COST_APPROVAL_IDENTITY_AND_PARITY`.
