# SBI Lightsail QA Bridge — prepared, not yet installed

A GitHub-hosted, manually triggered testing workflow to run a restricted read-only probe on the existing AWS Lightsail instance. This is **not** a general-purpose shell or an unattended deployment agent.

## Safety design
- This GitHub repository is public. Do NOT install a GitHub self-hosted runner on the PR129 financial application server.
- GitHub-hosted workflow is triggered only through manual workflow_dispatch, with an optional required approval environment named sbi-lightsail-qa.
- Lightsail user sbiqa has no sudo or Docker permissions. Its single SSH key is restricted with OpenSSH restrict and a forced command to a root-owned read-only probe.
- PostgreSQL role sbiqa has database CONNECT only, no financial table SELECT or DML permission.
- No invoice rows or secrets are printed. The report is stored as a GitHub Actions artifact for 14 days.
- Each new test script must be independently reviewed and installed. The public repository cannot replace the QA command automatically.

## Owner setup — Lightsail terminal
1. Generate a **dedicated** keypair on AWS (never disclose the private key in ChatGPT):

    ssh-keygen -q -t ed25519 -a 100 -N '' -f "$HOME/.ssh/sbi_qa_lightsail"

2. Download the two files from the pinned GitHub commit, avoiding ZIP upload:

    cd /home/ubuntu && mkdir -p sbi-qa-agent && cd sbi-qa-agent

    curl -fsSL https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/f77fca12398f345e4ffa06d9185a420c641cbb45/sbi-qa-agent/readonly_probe.sh -o readonly_probe.sh

    curl -fsSL https://raw.githubusercontent.com/sujitkumardolui154-ctrl/meghraj-reconciliation/f77fca12398f345e4ffa06d9185a420c641cbb45/sbi-qa-agent/install.sh -o install.sh

3. Review the files, validate syntax, then run the installation (this creates an unprivileged OS account, a matching catalog-only PostgreSQL role and forced SSH key):

    bash -n install.sh && bash -n readonly_probe.sh

    sudo bash install.sh "$HOME/.ssh/sbi_qa_lightsail.pub"

## Owner setup — GitHub
1. Review the draft PR, then merge to main when approved. Workflow_dispatch workflows must be on the default branch to appear in Actions.
2. Create repository Environment named sbi-lightsail-qa. Enable required reviewers if available on your plan.
3. Set environment secret SBI_QA_SSH_PRIVATE_KEY to the contents of the *dedicated* file $HOME/.ssh/sbi_qa_lightsail. Do not send it in chat or commit it.
4. Set environment variable SBI_QA_HOST to your current Lightsail public static IP.
5. On Lightsail obtain the server's actual public host key line (replace YOUR_LIGHTSAIL_IP with same address as SBI_QA_HOST):

    sudo awk -v host='YOUR_LIGHTSAIL_IP' '{print host, $1, $2}' /etc/ssh/ssh_host_ed25519_key.pub

6. Set environment secret SBI_QA_KNOWN_HOST to that full line. The workflow uses strict host-key verification.
7. Trigger GitHub Actions → SBI Lightsail restricted QA → Run workflow.

## Boundaries
- A PASS means PostgreSQL catalog/count, socket, and PR129 unauthenticated HTTPS response tests passed. It does NOT verify the PR129 database adapter, first financial import, Finance Engine, database restore or authenticated application end-to-end.
- Reports are accessible in GitHub Actions logs/artifacts. ChatGPT can read them through the connected GitHub app in a subsequent chat request; it cannot continuously access your SSH terminal by itself.
- If the port 22 firewall denies GitHub-hosted runners, add an approved secure network route; do not loosen database port 5432 or disable SSH host checking.
