# SBI Reconciliation — Mandatory Deployment Governance (Owner Direction, 2026-11-04)

These are mandatory instructions to every development, QA, release and deployment agent working on this repository. **If an action conflicts with these rules, STOP before the action, report the conflict and request a fresh, explicit owner decision.** A general instruction to "continue", "start", "next", or "finish migration" does not authorize a hosting, billing, identity-trust, traffic or financial-scope change.

## Locked mission and target

- **Migration source:** existing full Google Cloud Run SBI Reconciliation application (verify the actual deployed revision and backed-up data before parity claims).
- **Approved AWS destination:** the owner's **existing AWS Lightsail** SBI staging instance. Work toward full feature parity on this host first.
- **Not approved as default:** EC2, ECS, EKS, Lambda, API Gateway, identity-broker server, additional persistent instances or other billable hosting. Such alternatives are **proposal-only** pending owner approval of exact purpose, total incremental and recurring cost, and rollback/decommission plan.
- The user requested no unnecessary duplicate servers. Do not interpret an AWS price calculator estimate, creation of an IAM role, preliminary exploration, or a screenshot as consent to provision any paid resource.
- Existing Lightsail Docker services, public edge Caddy, Google Cloud Run, financial Firestore/database, Firebase identities, and GitHub workflows are protected. No live cutover, restart, deletion, unreviewed secrets/permission changes or financial write.

## Mandatory pre-change gate

Before a proposal crosses an architectural boundary, record:
1. **Why** it is necessary for the approved Lightsail-first goal; identify the specific evidence showing the current approach cannot meet requirements.
2. **Cheapest compatible alternatives**, including staying on Lightsail; distinguish required components from convenient or speculative extras.
3. **Scope delta:** list new services/accounts, data stores, identity providers, app behavior and network endpoints, including any vendor change.
4. **Full cost:** present both setup and recurring charges, in USD and indicative INR, including compute, storage, public IPv4, transfers, backup and taxes. Differentiate estimate from actual charges.
5. **Impact and rollback:** determine effect on production uptime, source-of-truth data, authentication, security, public exposure, rollback evidence and decommissioned duplicate resources.
6. **Explicit approval:** obtain a dedicated owner confirmation for the *specific* infrastructure change and costs before applying it. No implicit authorization from project ownership or previous approval.

If any element is absent: `ARCHITECTURE_CHANGE=BLOCKED_PENDING_OWNER_APPROVAL`.

## Identity and security

- Browser Firebase sign-in is NOT equivalent to Firebase Admin server credentials, session revocation and privileged user-management. Do not weaken checks to make Lightsail appear ready.
- Do not trust the Lightsail service-managed `AmazonLightsailInstanceRole` account `731738810135` as an application-owned WIF identity for AWS account `146415808408`.
- Existing Google WIF pool `sbi-aws-migration-pool` and provider `sbi-aws-lightsail` are owner-reported disabled. Do not enable, grant Firebase scopes or change trust policies without precise independent verification and explicit approval.
- New IAM role `SBI-Firebase-WIF-Stage` is created but **not attached to Lightsail**. Its existence is not a reason to provision EC2.
- Never request or store long-lived AWS keys, Google service-account private-key JSON, Firebase user passwords, tokens, sensitive account records or invoice/payment data in GitHub or chat.

## Financial and release safety

- Reconciliation/payment-write engine, financial database updates, user mutations, import Apply, public API opening and migration of source database are all blocked until approved independent QA, matched report values, authenticated end-to-end testing, backup/restore and rollback.
- Preserve 53-column source contracts, invoice/branch/SOL IDs as text, original financial database and approved financial output headers.
- Do not mark a test PASS without executed evidence. Distinguish source audit, synthetic test, isolated Docker build, real Firebase session test, AWS deployment and financial production acceptance.
- Keep Cloud Run and existing Lightsail live until a separately approved, feature-parity-verified cutover.


## Mandatory consolidated test execution (owner direction, 2026-11-04)

- **Always combine compatible checks into one executable batch** where possible. Plan checks before asking the owner to run commands; give a single copy/paste-safe one-line command or one versioned repository script instead of repeatedly requesting nearly identical commands and "next" messages.
- One batch should run relevant startup/config preflight, source/security contract checks, synthetic authentication, route-denial tests, existing-container and resource checks (read-only), and summarized outcomes **when these can safely share the same environment**. Do not combine stages with incompatible permissions or risk profiles.
- Clearly state any prerequisites, whether the batch starts a process or uses network access, its expected cost, cleanup/rollback and what is *not* verified. Default to offline/no-network/no-finance/no-deployment; never elevate a test to live production merely to combine steps.
- Each batch must return individual check results, one final `BATCH_QA=PASS|FAIL|BLOCKED` marker, meaningful nonzero exit status on failure, and `NEXT_GATE`. A partial pass must not be labeled a whole-batch PASS. Archive only non-sensitive test evidence; do not leak secrets, PII, auth tokens or financial records.
- Avoid rerunning previously passed checks unless source, dependencies or environment have changed or an acceptance gate specifically requires retesting. Use pinned commits and unique image tags to avoid stale artifact tests.
- If a prerequisite is unknown, let the combined script check it and report `BLOCKED` with a specific next action rather than asking the owner to repeat an earlier test. Do not hide any skipped or unexecuted checks.
- Preserve separate explicit approval gates for paid infrastructure, cloud IAM/WIF changes, real Firebase Admin login, financial reads/writes, production traffic changes and cutover. **Test consolidation never grants authorization.**

## Practical engineering workflow

- Prefer one consolidated safe test over repeated small copy/paste shell commands. Commands to the owner should be single-line where practical because multiline commands previously broke in the Lightsail browser terminal.
- Before expensive build repeat, inspect image/build status and environment resource capacity.
- Never run destructive cleanup, broad IAM changes, backup deletion, production deploy or billable provisioning from unreviewed staging tasks.
- Change source in a feature branch with CI, evidence and review. A green CI test does not authorize infrastructure changes.

**Current deployment decision: LIGHTSAIL_FIRST; EC2_PROPOSAL_ONLY; FINANCIAL_WRITES_BLOCKED; PRODUCTION_CUTOVER_BLOCKED.**
