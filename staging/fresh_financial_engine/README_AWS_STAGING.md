# NEW engine 21 11 2026 — AWS synthetic staging deployment

This deployment is an **independent local-only canary**, *not financial production*. It runs on the existing AWS host beside the unchanged SBI Workspace, but it does not use Caddy, Firebase, historical files, payment evidence uploads or finance DB. The service **cannot receive invoice/payment content**. Only its internally hardcoded synthetic demo can invoke the proposal engine.

## Run from a clean, exact SHA-pinned checkout on AWS

```bash
bash staging/fresh_financial_engine/deploy_synthetic_aws.sh
```

The script inspects the checked-out commit, requires a clean tracked worktree, builds the single staging container from `Dockerfile.synthetic`, starts it on **127.0.0.1:18087 only**, checks health, executes one fabricated-only engine demo, and confirms POST Apply is **403**. It does **not** open any public web route, touch production Caddy or existing containers, change financial data, or enable Apply.

Check status:

```bash
curl -fsS http://127.0.0.1:18087/healthz
curl -fsS http://127.0.0.1:18087/api/synthetic-demo
```

Rollback this isolated stage (run from its git worktree):

```bash
SBI_REVIEWED_SOURCE_SHA="$(git rev-parse HEAD)" sudo -E docker compose -f staging/fresh_financial_engine/compose.synthetic.yaml down
```

Do not deploy this service to the production reverse proxy, attach any money-related volume, introduce real invoice/UTR endpoints, or merge it as a production financial service. For an actual new-only production release, missing authenticated evidence, approved master/ledger, corrected writer, accounting exceptions and independent financial QA must be implemented and signed off separately.
