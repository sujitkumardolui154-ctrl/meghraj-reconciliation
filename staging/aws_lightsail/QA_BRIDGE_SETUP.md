# SBI AWS QA bridge — one-time connection

Goal: **DIL writes code to GitHub → approved changes trigger GitHub Actions on an isolated AWS QA runner → run logs and pass/fail appear in GitHub for DIL to read.** No more copying ordinary test output into chat.

## Critical separation

**Do not install this runner on `/home/ubuntu/sbi-aws-app` or the existing Lightsail production instance.** A GitHub self-hosted runner executes repository job code at OS level. A separate disposable AWS QA VM/account with **no access** to production databases, service credentials, Docker socket, private production networks or financial exports is necessary.

The AWS QA machine must be non-privileged, outbound-only HTTPS (443) for GitHub, with no inbound SSH from the public Internet unless you deliberately use a secure administrative channel. Register the runner at the repository level only after restricting repository write/merge permissions and enabling branch protection / mandatory review on `main`. Never use a public-repository self-hosted runner for untrusted pull requests.

## One-time operator setup (after independent isolation is verified)

1. Create a *separate* AWS QA VM with a dedicated unprivileged runner account and no permissions to manage other AWS services. Install Python 3 and use a supported Linux distribution.
2. GitHub repository → **Settings → Actions → Runners → New self-hosted runner**. Follow GitHub's current official Linux installation instructions **on this QA VM only**. Keep the short-lived registration token on that machine; never paste it into chat or commit it.
3. Register the runner with label `sbi-aws-qa-isolated`. Ensure the default `self-hosted`, `linux` and `x64` labels remain. Limit runner access to this repository.
4. Explicitly set the runner's account-level environment variable `SBI_AWS_QA_ISOLATED=true` only after confirming the VM has no access to financial data or credentials. This variable is a check, **not isolation itself**.
5. Prefer an ephemeral runner that is discarded/rebuilt after every job. A persistent runner is vulnerable to workload persistence and requires routine security maintenance and cleanup.
6. Have a reviewer approve/merge the workflow into protected `main`. It **cannot automatically start from an unmerged feature branch** because this job requires the trusted `main` ref.
7. After merge, run **Actions → SBI AWS Private QA Bridge → Run workflow** on `main` once. Subsequent changes to the listed files merged into `main` trigger it automatically. Review logs and summaries in Actions.

## Safety

- This workflow does not use SSH, access production AWS, call Firestore or invoke Docker.
- Does not expose secrets. Never place a financial database key or privileged AWS IAM instance role on the QA runner.
- Workflow only runs from the exact repository's `main` branch; not from PR refs.
- All changed workflow files and Python test code must be reviewed before merge, since tests can execute arbitrary Python.
- Only synthetics and source checks; a success is **not** production security approval.
- DIL can read workflow outcomes with GitHub access when you ask, or a separately authorized monitor can read them on a schedule.
- Connecting this runner does **not** give ChatGPT unrestricted shell access. The GitHub workflow is the approved execution boundary.

## Progress

After connection, inspect the [repository Actions page](https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions) for PASS/FAIL and logs. A queued job indicates runner offline or mislabelled; a passing workflow is not evidence that the financial production application was deployed.
