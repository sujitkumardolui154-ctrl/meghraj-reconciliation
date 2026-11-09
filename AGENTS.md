# SBI Reconciliation — Engineering Execution Rules

## ADMIN RULE WS-LOCK-001 — STRICT WORKSTREAM ISOLATION

**Existing owner-admin rule, retained without relaxation.** Scope intended by the owner: all current and future project chats and workstreams. This repository file enforces the rule for work performed **within this repository**; it does not itself configure unrelated ChatGPT projects.

1. **ONE CHAT / PAGE = ONE WORKSTREAM.** A chat remains dedicated to its assigned project workstream. Keep unrelated tasks, code, tests, deployments and source files in separate appropriate chats.
2. **Conflict response (exact):** `WORKSTREAM CONFLICT — ACTION BLOCKED`. Explain the conflicting workstream and direct it to its own chat. **Do not execute, modify code, run tests, stage, deploy, or expand scope** for that conflicting task in the current workstream.
3. A new user request within an existing workstream is not automatically authorization to merge separate workstreams. Preserve all existing locks, business rules and safety gates. Changes to WS-LOCK-001 itself require **explicit owner authorization**.
4. **Owner-approved addendum WS-LOCK-001.A — LAST-WORKING-FIRST / EXACT-SCOPE / MINIMAL EXECUTION (9 November 2026):** Within the **authorized active workstream only**, before creating code, issuing a new terminal command, building, testing, deploying or making other changes:
   - **First recover the last verified working state** for that workstream: relevant branch and exact commit, deployed artifact/revision and runtime health if applicable, latest successful relevant QA, backups and rollback. Record timestamp and source of evidence. Clearly mark unknown values and do not assume local Git HEAD equals the live deployment.
   - **Then identify the owner's exact requested change** against existing implementation. Reuse last-working files, tools, reports and CI evidence; prefer **NO CODE CHANGE** whenever the requirement is already met or can be resolved without new code.
   - **Execute only what is necessary**, selecting the smallest safe diff and mandatory affected regression tests. Skip redundant commands, repeated testing, duplicate implementations, unnecessary builds, infrastructure and cloud costs. A status-only request must not trigger implementation or QA.
   - **Stop safely on missing proof** that is necessary before a write, deployment or release. Provide the single minimal read-only verification step instead. Never bypass authorization, finance write protections, original source preservation, independent parity, security or rollback gates merely to reduce work.
   - **Reporting contract:** `LAST_WORKING_VERIFIED / NOT_VERIFIED | WORKSTREAM | EXACT_REQUEST | NO_CODE_CHANGE / MINIMAL_DIFF | QA_REUSED / QA_NEEDED | BLOCKER | NEXT_SINGLE_ACTION | FINANCIAL_WRITES / TRAFFIC_CHANGES`.
5. This addendum does **not** replace the isolation rule. It **applies after** the workstream is confirmed. In this project's current authorized AWS deployment workstream, the active hosting target remains **existing AWS Lightsail**, and legacy GCP migration work is a separate workstream unless the owner explicitly reauthorizes it.

---

**Owner instruction (9 November 2026): LAST WORKING FIRST.** These instructions apply to coding, deployment, reconciliation, migrations, tests, and assistant/agent maintenance. They supplement, never override, the stricter financial, security, audit, and rollback requirements.

## 1. Recover and verify the most recent working state BEFORE planning or generating new code

1. Determine the **current user-selected destination** from the user's latest explicit instruction. The active deployment target is the **existing AWS Lightsail host** unless the owner expressly reauthorizes another target. Google Cloud migration research, old PRs, and passing Cloud Run source QA are **not** authorization to switch platforms.
2. Inspect the **last known working** repository branch and exact full commit, current checked-out host branch and commit if available, live container image IDs and embedded revision labels, service/health evidence, previous deployment receipt, immutable backup/rollback proof, latest relevant CI pass, open PRs, and existing code/scripts. Reuse evidence already verified; refresh only what has become stale or disputed.
3. Distinguish **observed working**, **historically reported working**, **source-only QA passed**, **running service**, and **not verified**. Never infer a deployed version merely from local `git rev-parse`, a green GitHub check, or an existing container. For the AWS host the user most recently reported local `aws/lightsail-preview-20261102` at abbreviated `b10420c`, but **live Docker containers and deployment revision were not verified** because the audit command failed. This is a *reference for checking*, not a certified working deployment.
4. Maintain one concise evidence ledger per requested change: **Last working (source SHA / runtime image / timestamp / evidence), exact requested behavior, minimal file diff, affected tests, planned rollback, current blocker, next action**. If the baseline cannot be established with available tools, **STOP before write/deploy** and report the one missing proof.

## 2. Execute only the exact requested change

- First map the requirement to current implementation and identify the smallest change. Prefer a **no-code correction** (existing setting, documentation, command fix) when it fully solves the request.
- Do not create duplicate apps, agents, dashboards, routes, repositories, databases, infrastructure or deployment branches merely because a user says “start”, “next” or “update”. Do not migrate to GCP, provision additional AWS resources, change cloud identity or reconnect financial services without **new explicit scope-specific authorization** and mandatory gates.
- Never overwrite verified working files or custom on-host changes. Preserve provenance; write a small scoped draft PR for necessary source modifications, not a blind production patch. A docs-only rule change does not need Docker builds or finance QA.

## 3. Avoid unnecessary code execution and repeated tests

- **Inspect first, run second**. Use known read-only results, GitHub source and exact-head CI evidence where still valid; don't repeat expensive builds/scans or issue multiple terminal commands for the same result.
- Run only the **minimum change-scoped tests** needed for safety, plus mandatory related regression gates. Combine compatible read-only checks into **one** safe, copy/paste-proof command. Keep shell commands on single lines where line continuation is error-prone; never paste partially split arguments. Do not print credentials, raw financial rows, tokens, or environment secrets.
- Do not run deployment, migration, import/apply, payment allocation or financial database writes as a “test.” An independently authenticated real-data read or live service call needs its own access authorization; do not represent synthetic coverage as live acceptance.
- Before each tool, code or command action, be able to state what **new necessary evidence** it will add. If none, skip it.

## 4. AWS-first change and release gates

- Existing AWS Lightsail preview must remain available and unmodified unless the owner specifically approves a scoped change. Keep any new runtime on isolated services/ports with no financial write access, private authentication, image digest/commit traceability, and rollback evidence.
- First compare host actual container state with repository source; no deploy on a guessed image label. Preserve existing web/Caddy paths and manually edited dashboard assets.
- Original SBI source and financial contracts remain immutable (PAYMNENT A:L including credit I; invoice S protections; approved 53-column projection and 18-column Credit Note schema). No release without real independent parity, authentication and isolated restore.
- No auto-merge, no architecture change, no new public finance endpoint, no cloud IAM grant, no production traffic change or financial write based solely on QA or owner business-rule approval.

## 5. Mandatory short progress format

Report only:

- **Last working verified:** commit, image/revision, runtime/endpoint and evidence timestamp, explicitly marking anything still unknown
- **Requested change:** exact scope and smallest action
- **Changed:** files, PR/commit (or `NO_CODE_CHANGE`)
- **QA:** reused vs newly executed; source CI vs live runtime distinction
- **Current blocker / next single necessary action**
- **Safety:** production traffic, financial writes and recovery proof statuses

If user asks only for a status update, **audit and report**; do not generate code, rerun QA, create PRs or provision cloud services.

**Priority:** Owner's most recent explicit instructions override older workflow preferences regarding active target and requested scope; safety/financial restrictions remain in force.
