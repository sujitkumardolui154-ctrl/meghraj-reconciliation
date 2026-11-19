# SBI AWS dashboard visual refresh — 19 November 2026

## Owner-approved scope
- Midnight navy, refined teal/blue accents, professional typography and responsive tab row.
- Remove "Supervisor API Monitoring" section and its automated polling from dashboard.js.
- Remove "Backend API Reports" section and stale links from the Dashboard main view.
- Control Tower remains a tab within the same authenticated dashboard, not a navigation link.
- Preserve the Engineering Control Tower original monitoring data, API routes and original standalone page.
- Preserve Firebase v1.5 login, reports/database tabs, existing /pipeline Basic Auth and financial write locks.

## Security and history
The previous tab fix may or may not have been activated by the operator. The new
deployment therefore allows activation only when Caddy matches EXACTLY one of:
- staging/aws_login_v150/Caddyfile.control_tower (previous source-backed tower)
- staging/aws_login_v150/Caddyfile.control_tower_tab (same-page tab fix)

Unknown Caddy changes are blocked; no force overwrite.
Deploy script is pinned to one reviewed full SHA. New separate container
sbi-dashboard-polish-stage; existing live containers remain unmodified.
Caddy is backed up separately to /etc/sbi-aws-login-v150/Caddyfile.before-dashboard-polish
before activation, with automatic and manual rollback support.

## Staging then activation
sudo bash staging/aws_login_v150/deploy_dashboard_polish.sh stage FULL_SHA
Verify DASHBOARD_POLISH_STAGE=PASS before executing:
sudo bash staging/aws_login_v150/deploy_dashboard_polish.sh activate FULL_SHA

Manual rollback (only when public config still matches candidate):
sudo bash staging/aws_login_v150/deploy_dashboard_polish.sh rollback FULL_SHA

Browser acceptance:
- open /dashboard after Firebase login; verify new theme
- Control Tower switches in-page; main dashboard header stays visible
- Dashboard, Reports and Database Update tabs still switch
- no Supervisor API Monitoring section
- no Backend API Reports section
- original /pipeline remains under existing Basic Auth
- financial writes disabled; production cutover BLOCKED

Do not merge into production or enable financial APIs through this UI-only release.
