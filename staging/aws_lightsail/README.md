# AWS Lightsail preview hosting — preparation only

This is a **public HTTPS URL protected by login**, serving the isolated SBI *placeholder* from `../railway_public`. It contains **no financial database, invoice data, imports, Firestore connection, or backend forwarding**. The full SBI application is not yet migrated.

## Budget and prerequisites
- Lightsail Linux IPv4 plan: $7/month for 1GB or $12/month for 2GB (plus tax, optional snapshots, DNS or extra usage); prices vary by location and may change.
- Use a dedicated Lightsail Ubuntu 24.04 server. Configure AWS Budgets billing alerts; not a hard spending cap.
- Create a Lightsail static IP, point a domain A record to it, open TCP 80 and 443. Restrict TCP 22 to your administrator IP; do not expose 8080.
- Install Docker Engine and Docker Compose from official Docker packages, following current Ubuntu instructions.
- This PUBLIC source repository has no secret values and no financial data. Never commit `.env`, payment records, backup exports, or credentials.

## Server setup (after AWS account/instance/domain prepared)
```bash
git clone https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation.git
cd meghraj-reconciliation
git fetch origin aws/lightsail-preview-20261102
git checkout aws/lightsail-preview-20261102
cd staging/aws_lightsail
cp .env.example .env
chmod 600 .env
# Edit .env with your real domain, chosen username, and a NEW high-entropy 20+ character password.
# Do not display/copy credentials into chat.
docker compose config --quiet
docker compose up -d --build
docker compose ps
```
Only run after DNS points at the static IP; Caddy provisions HTTPS certificates.
Check that `https://YOUR_DOMAIN/` returns 401 without login, 200 with valid credentials; `/api/imports/apply` stays 403 with login.
`/healthz` reports only non-financial status. For real financial app, implement stronger authentication than HTTP Basic.

## Rollback
Run `docker compose down` from this directory; leaves volumes intact and does not affect Google Cloud. Do not move DNS away from existing production.
No CI auto deploy, no AWS credentials stored in GitHub.

## Security acceptance
- Image source is only the isolated preview.
- No connection to Google Cloud or financial backend.
- No secret in Git.
- Review Docker pinned dependencies, updates, HTTPS and host firewall before public launch.
- No full-production go-live until original financial baseline and 13 outstanding exception entries reviewed, independent engine tests and rollback pass.
