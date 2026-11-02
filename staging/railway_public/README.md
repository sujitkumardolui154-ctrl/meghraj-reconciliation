# SBI Railway public URL / protected preview

**Not the complete SBI application.** Public-facing login-protected placeholder only. No Firestore, Google Cloud, invoices, uploads, payments, backend proxy, or financial write paths. Do not treat this as financial-production release.

## Deploy manually with Railway
1. Create a Railway project from this GitHub repository, using branch `railway/public-login-staging-20261102`.
2. Set service **Root Directory** to `/staging/railway_public`. Leave other application services unconnected.
3. Before any deployment, add service variables `PREVIEW_USERNAME` and a unique random `PREVIEW_PASSWORD` of at least 20 characters. Set them in Railway, never GitHub source or chat.
4. Enable a generated Railway public HTTPS domain for this service.
5. Test `/healthz` returns only general status; homepage returns 401 without login and 200 with valid credentials.
6. Configure spending alerts and resource limits. Railway may charge above $5 included usage.

## Gate
No financial data or application source migration until sanitized source and approved database migration pass independent QA. Google Cloud production traffic and resources remain unchanged.
