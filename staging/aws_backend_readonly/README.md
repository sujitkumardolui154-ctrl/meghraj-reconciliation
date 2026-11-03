# SBI AWS read-only backend packaging — SOURCE ONLY

This is a **non-deployed, isolated staging scaffold** for the next AWS backend
migration stage. It does not certify the reconciliation engine, read real SBI
invoices or move private financial data.

- The image copies only the sealed gateway app; **not** backend_source/main.py,
  uploader, importer, payment engine or Firestore writer code.
- Liveness: GET /healthz is 200 and reports financial_data_connected=false.
- Business readiness: GET /readyz is 503 until independent data certification.
- Allowed protected report routes: GET /reports and GET /reports/<approved>.csv.
  They require a separate operator-local Basic account with a >=24-character
  password and currently **always return 503**. No report data is returned.
- All writes and unrelated routes are rejected.
- Manual QA Compose is independent of the live AWS public-preview Compose:
  a distinct profile, loopback-only port 18086, UID 10001, read-only filesystem,
  no volumes, internal network, and no access to external financial services.
- GitHub Actions runs synthetic HTTP/deny tests and a no-network non-root image
  smoke test, but does not deploy.

**Do not run this image as production.** No new IAM, Firebase claims, AWS
credentials, automatic releases, financial writes or data copying is authorized.
Never add .env, passwords, cookies, database exports, customer records or tokens
to GitHub. Use independent credentials; do not reuse the AWS public preview
login. The existing AWS Lightsail preview, staging executor, Caddy, dashboard,
chatbot and financial database are left untouched.

Before any manual staging run, separately review the image source SHA,
least-privilege auth, private input evidence, 53-column report integrity,
rollbacks, read-only Firestore migration strategy and formal QA approval.
A green source test is not a deployment or financial release.
