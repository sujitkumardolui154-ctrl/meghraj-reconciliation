# SBI AWS Stage 5E — K01/M02 isolated hardening preflight

Status: source candidate, manual AWS review required. Does NOT change Cloud Run login-v150, public AWS preview, running containers or financial data.

## Stage 5D owner-observed facts (4 Nov 2026)
- sbi-agent-stage image sbi-stage-candidate:11c3166728a8: uid=0, CapDrop=[ALL], SecurityOpt=[no-new-privileges], root filesystem writable.
- sbi-dashboard-ui-stage image caddy:2: uid=0, default capabilities, no explicit SecurityOpt, root filesystem writable.
- Both are on Docker bridge, published only on localhost 18082/18081; the public Caddy/preview pair uses another Docker network.

## First manual command: inspect only
```bash
cd ~/sbi-aws-app || exit 1
git fetch origin feature/sbi-aws-stage5e-hardening-preflight-20261104
git show origin/feature/sbi-aws-stage5e-hardening-preflight-20261104:staging/aws_lightsail/stage5e_hardening_preflight.py > /tmp/sbi-stage5e-preflight.py
sudo python3 /tmp/sbi-stage5e-preflight.py
```

## Optional separate command: disposable synthetic smoke
```bash
sudo python3 /tmp/sbi-stage5e-preflight.py --smoke
```
This creates only temporary network-disabled Docker test instances (--rm), with no host mounts, no published ports, no finance credentials and a read-only root filesystem. It runs a small Python identity command and Caddy version; it DOES NOT start the actual services or establish production compatibility. Failures require investigation and do not justify touching running containers.

## Before real hardening deployment
1. Confirm non-root service start with existing dashboard content and authentication, including Caddy /data and /config write/persistence requirements.
2. Verify health, localhost port binding, role boundaries and network isolation using separate candidate names.
3. Preserve agent CapDrop=ALL and no-new-privileges.
4. Verify image identity, rollback and authenticated functional parity before any promotion.
5. Require separate explicit release approval. Financial execution remains restricted.

This is a security preflight, not migration of the existing Cloud Run dashboard UI.
