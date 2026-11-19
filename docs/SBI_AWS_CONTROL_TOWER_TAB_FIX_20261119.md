# SBI Control Tower tab fix — 2026-11-19

## Problem

Authenticated Login v1.5 dashboard showed Control Tower as a regular anchor (href=/control-tower).
Clicking it replaced the browser document instead of switching tabs inside the dashboard.

## Fix

- Control Tower is now a button with a hidden content panel within the existing dashboard.
- An iframe loads the same-origin Firebase-protected Control Tower lazily, only when the tab opens.
- Dashboard CSP allows same-origin framing (frame-src self) only.
- Embedded Control Tower hides duplicate top nav; only ?embedded=1 allows same-origin framing.
- Direct standalone /control-tower continues to deny embedding.
- Clicking any other tab hides the Control Tower and restores existing navigation.
- Engineering monitoring APIs remain read-only. Financial writes and task editor are blocked.

## Safe release

Use pinned separate worktree and deploy_control_tower_tab.sh stage FULL_SHA, then activate FULL_SHA
only after QA, private HTTP PASS and operator review. This runs a new candidate container
sbi-login-control-tower-tab-stage, retaining the previous Control Tower and original Login v1.5.
The current Caddy configuration is backed up before activation. The former /pipeline
Basic Auth and blocked financial API access remain intact.
