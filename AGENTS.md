# SBI Reconciliation Workspace — Repository Agent Rules

## Mandatory development QA reuse rule (owner-approved, 28 Nov 2026)

**BEFORE running any deployment, database, Firebase, reconciliation, invoice, GST, network, HTTPS/mTLS or other QA/test workflow:**

1. **Search this GitHub repository first** for already-implemented tests, current/previous development-module branches, workflow logs, and reusable AWS operator receipts. Check the relevant development area and \`development/qa_reuse/\` evidence register. Do not assume that a test is missing because it was implemented in a different module.
2. **Verify evidence, not labels:** compare test purpose and security scope, exact GitHub run/workflow and its latest conclusion, executed commit, relevant source/config fingerprints, and environment identity. A synthetic TLS PASS only proves synthetic TLS; local Flask/private PostgreSQL QA does not prove external HTTPS/mTLS.
3. **Select only required QA.** Reuse an unchanged, valid completed PASS across modules. Rerun only tests affected by changed source/configuration, failed or missing evidence, newly introduced behavior, or environment-specific deployment changes. Do **not** rerun an entire historical combined suite without a real dependency or release requirement.
4. **Use a separate development QA module** to inventory tests, classify dependencies, and produce the minimum target-test plan *before execution*. The canonical instructions are \`development/qa_reuse/QA_EXECUTION_RULES.md\`, evidence is \`development/qa_reuse/evidence_registry.json\`, and the read-only planner is \`development/qa_reuse/delta_qa_gate.py\`. The invoice/GST selector on \`feature/sbi-module-qa-reuse-policy-20261128\` remains independently scoped until integrated.
5. **Fail closed:** if GitHub evidence is unavailable, the matching source is changed, the latest relevant workflow failed, or the target security scope differs, do not mark PASS or bypass the check. Review or run the **specific affected** test; explicitly document gaps. Do not disable scanners or rewrite approval flags to obtain a green result.
6. **Release-critical live acceptance is never waived** by offline/synthetic QA: current external HTTPS/mTLS, authorized QA DNS/FQDN and client CA, certificate revocation, real Firebase expired/revoked sessions, PostgreSQL cross-tenant RLS through live ingress, backup/rollback and independent sign-off must each have applicable evidence before release.
7. **Financial Apply and production release remain LOCKED** until the authorized release process separately approves them. No historical financial writes, role/credential/proxy/DNS changes, or secret disclosure are permitted as shortcuts.
8. **Report QA decisions before execution** as REUSE / TARGETED_TEST_REQUIRED / BLOCKED_MISSING_EVIDENCE / LIVE_ACCEPTANCE_PENDING, with the exact supported evidence references. Never claim background automation or an existing PASS for a test that has not run.

### Scope and integration

These rules apply to all development and deployment workflows on this branch. They are a repository development instruction and QA-planning policy, **not themselves an enforced GitHub branch protection rule**, release approval, or proof that all pending tests were performed. Do not claim this rule has reached the default branch unless it has actually been merged. Before starting a new release, make sure the executing checkout includes these instructions and the QA reuse module.

When writing new tests, register their scope and expected reuse conditions in the separate development QA module. Where safe and approved, integrate the planner into deployment CI as a required pre-execution step. Its current implementation is read-only and does not dispatch tests.
