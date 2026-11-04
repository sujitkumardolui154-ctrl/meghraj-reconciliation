# SBI existing Lightsail host — GitHub test bridge (single-server option)

The user opted to run GitHub test jobs on the **existing Lightsail server** rather than create another instance.

## Important risk

A self-hosted GitHub runner executes checked-out code, tests and workflow shell scripts with its local Linux account permissions. **Using the same production server is not isolation**. A compromised runner/job could access any data, open localhost ports, exploit OS privilege escalation or interfere with the production server. Dedicated users and no-Docker-group membership reduce risk, but **do not eliminate it**. For higher assurance use a separate instance.

The design below is for **trusted, synthetic, non-deploying QA only**, no pull-request jobs. Financial execution remains restricted. Never allow third-party/untrusted code to be merged into protected `main`.

## 1. One-time operator account setup on existing Ubuntu host

Before configuring, verify a snapshot/backup exists and production containers are healthy. In the existing Ubuntu terminal, as an administrator:

```bash
sudo adduser --disabled-password --gecos "" sbi-qa-runner
sudo usermod -L sbi-qa-runner
id -nG sbi-qa-runner
```

The dedicated account must not belong to `sudo`, `docker`, `adm`, `lxd` or similar privileged groups. Do **not** add it to them. Do not put the runner in the main application directory or grant it read permissions on financial data, .env files, key files, production docker sockets, deploy scripts or credentials.

Use `sudo -u sbi-qa-runner -H bash` only to enter this account for setup (run registration commands as **sbi-qa-runner**, not root). Install the GitHub runner only into a directory owned by that account and accessible exclusively to that account. Avoid a systemd service requiring root until its unit permissions and execution account have been reviewed.

## 2. GitHub one-time registration

Go to **Settings → Actions → Runners → New self-hosted runner** in repository `sujitkumardolui154-ctrl/meghraj-reconciliation`; use GitHub's live Linux/x64 instructions and keep the short-lived registration token entirely within your AWS terminal. Never paste runner tokens in ChatGPT, GitHub issues or commits.

Run the GitHub-supplied runner download and configure commands under `sbi-qa-runner`; set label **`sbi-aws-qa-samehost`** and exact runner account. Set environment marker `SBI_AWS_QA_SAMEHOST_ACK=true` in the runner user's process environment *only after* acknowledging the shared-host risk and verifying its permissions. This marker does **not** enforce security or serve as approval to deploy.

Use the runner foreground mode `./run.sh` for first-time verification. The account must have no AWS IAM permissions, no Google application credentials, no Docker group access and no financial database access. Limit runner access to this one repository.

## 3. GitHub workflow activation

After a reviewer approves and merges PRs #42 → #45 → #47 → #48 to a **protected main** branch, run the workflow `SBI AWS Private QA Bridge` from `main` using GitHub Actions UI. The initial branch PR workflow cannot execute this job because it requires `github.ref == refs/heads/main`.

Every future merge into main involving the selected files triggers automatic **synthetic** tests from the same host. CI logs and the step summary return to GitHub; DIL can review those results using GitHub access. No need to paste normal test output into chat.

## Explicit restrictions

- This workflow uses only `actions/checkout` and `python3 -m unittest` and static checks. No SSH, deployment or Docker commands.
- It does **not** test or deploy the live containers. Existing four containers remain untouched.
- Import apply/preview execution remains blocked by code for `aws-hmac-v1`; this runner never uses real invoices.
- Logs can be copied from GitHub when requested; continuous autonomous code development or autonomous inspection needs a separately authorized scheduler.
- Do not treat environment flag checks as isolation. Real host file permissions, group membership, kernel isolation and network permissions matter.
- Installing runner services, adding credentials or merging untrusted changes creates new risk and requires another review.
