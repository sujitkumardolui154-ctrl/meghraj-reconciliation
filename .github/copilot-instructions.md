# SBI Reconciliation Workspace — Development QA Rules

When planning or running deployment, security, reconciliation, invoice, GST, database, API or integration tests:

- First search GitHub branches, dedicated development modules, workflows, prior completed GitHub Actions runs, source fingerprints and available prior AWS operator evidence. Existing tests in another module are candidates for reuse.
- Consult \`AGENTS.md\` and the separate \`development/qa_reuse/QA_EXECUTION_RULES.md\` rules before executing a new suite.
- Reuse a past PASS only if it is the same relevant test scope with a completed successful latest exact workflow/commit, byte-identical relevant source and unchanged critical environment. Record the workflow URL, run ID, commit and scope.
- Run only delta QA for changed/failed/unverified paths and direct dependencies. Do not repeat broad combined tests merely because a development milestone changed its name. Unknown changes or unavailable proof cannot be called PASS.
- Preserve independent release gates: real external mTLS is not equivalent to synthetic localhost TLS, Firebase private in-process sessions are not external HTTPS acceptance, and offline PKI metadata is not certificate/revocation testing.
- Do not skip failed scanner findings, change security policy to force a PASS, print secrets, or write to real bank data. Production financial Apply and release remain LOCKED absent separate authorization.
- New test coverage and reuse decisions belong in the separate development QA module; update its registry and targeted tests, not historical modules.

**Status:** This is a development instruction, not GitHub branch protection or a production deployment approval. Follow the least-privilege and exact-evidence rules in \`AGENTS.md\`.
