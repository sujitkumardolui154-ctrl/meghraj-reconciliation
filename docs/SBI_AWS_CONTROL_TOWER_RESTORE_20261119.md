# 2026-11-19 — AWS Control Tower integration (read-only)

Historical SBI Engineering Pipeline Control Tower:
- staging/railway_public/pipeline.html — original layout, release gates,
  priority board, A–N workstreams, blockers, tasks and version logs
- staging/railway_public/pipeline_data.py — read-only cached GitHub evidence
- staging/railway_public/app.py — older *separate* Basic Auth preview

The prior 8eebfd40815f77eded0a8fb48457c796f98329f0 Login v1.5 build
included dashboard_source/index.html but not the engineering Control Tower.

This feature bundles unmodified pipeline.html and pipeline_data.py in the
Firebase-protected login image. It adds:
- /dashboard -> Control Tower navigation link
- /control-tower -> original source-backed visual with back-to-dashboard link
- /control-tower/api/pipeline/status, version, history.csv -> Firebase-guarded
- /control-tower/api/priority-tasks -> UNAVAILABLE (503) until independently
  connected, rather than falsely showing an empty existing task DB
- POST/PUT/PATCH/DELETE -> 403, no financial/owner mutations

Existing /pipeline remains on previous Basic Auth container. No financial
database or read/write connection is introduced.

## Release protection

Original installed config: staging/aws_login_v150/Caddyfile.phase1
Candidate config: staging/aws_login_v150/Caddyfile.control_tower
Use dedicated deploy_control_tower.sh stage|activate|rollback FULL_REVIEWED_SHA.
Only after synthetic QA, SHA verification, private HTTP PASS, and backups may
the public Caddy routing change. The existing v1.5 login container remains
running to permit rollback; the original six AWS containers are untouched.

Production financial cutover and payments/credit note updates remain BLOCKED.
