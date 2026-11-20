# SBI Database Update navigation change — 20 November 2026

Baseline: AWS Control Tower v2 at 15b475e047ac420213fb57acd031d7bec8f2090d.

## Scope
- Move the existing disabled "Excel Upload — Dashboard v1.3.0" section (and its original handler) out of the Dashboard page and into Database Update > Invoice Data & Excel Upload. Preserve the existing invoice import-preview / receipt / rejection-log workflow without changing backend APIs.
- Add a second local Database Update view "Payment Reconciliation" with an explicit payment evidence upload entry, a three-step planned verification workflow and disabled buttons. This is a UI option, NOT an operational payment upload or financial engine deployment.
- Current AWS read-only login service denies /api/* financial actions. Payment upload, matching, allocation, financial database writes and reconciliation must remain unavailable until a separate explicitly authorized verified backend and QA gate.
- Keep Dashboard, Reports, Control Tower v2, private notes and tasks, Firebase auth, and the existing /pipeline preview unchanged.
- Do not restart or reenable any paused ChatGPT scheduled automations.
- Run scoped UI and security tests and isolated Docker candidate before any AWS staging. Existing protected SQLite workspace must remain mounted without schema migration.

## Release
Use a separately pinned candidate/container behind the existing Caddy service. Confirm exact current Caddy baseline and running Control Tower v2 stage before activation; preserve old image and rollback route.
