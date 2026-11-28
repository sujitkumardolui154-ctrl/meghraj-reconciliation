# DB-R31.11.4U — Targeted Scanner Remediation

Date: 2026-11-28
Scope: source-only security scanner correction; no AWS deployment or database writes.

## Root cause
The existing `migration/check_public_tree.py` scanner rejects any tracked file containing a literal PEM private-key header. The R31.11.4K test `test_reject_unknown_fields_secrets_and_type_confusion` intentionally used that exact synthetic header as an invalid approval packet value. GitHub Actions run 46121221654 failed its public-tree check on this test file. The fixture is demonstrably a dummy marker without key material, but the scanner cannot distinguish intent.

## Minimal fix
Modify only `staging/aws_login_v150/test_r31_11_4k_external_mtls_readiness.py` to join two constant fragments at runtime when constructing the rejection test value. The runtime input to `k.read_packet` is unchanged and must still raise `GateBlocked`. Keep scanner patterns, source protections, approval logic, and security checks intact. Do not exempt the flagged file or disable scanning.

## Required targeted QA
1. `python3 migration/check_public_tree.py` must exit 0 and report zero issues.
2. Run only `python3 -B -m unittest discover -s staging/aws_login_v150 -p 'test_r31_11_4k_external_mtls_readiness.py' -v`.
3. Verify the runtime marker still causes the rejection test to pass.
4. Review new workflow job result on this exact commit; do not claim PASS before a completed successful run.

## Preserved earlier evidence
R31.11.4T verified three exact-source GitHub reuse decisions: 4J synthetic TLS, 4O DNS design, 4P PKI design. No rerun is needed unless affected sources drift. The 4U fixture change does not authorize replay of those suites.

## Release gates
- External R31.11.4S acceptance: 0 of 22 executed by this change.
- Seven live external security/release gates: pending.
- Finance Apply: LOCKED.
- Production release: BLOCKED.

No production database, Caddy, DNS, Docker, Firebase, or AWS configuration changes are made in this milestone.
