# OWNER MANDATORY DEPLOYMENT POLICY — 2026-11-20

**Precedence:** Owner's instruction on 2026-11-20 supersedes any earlier D-022/D-023/D-024 proposal that calls for using previous financial records to calculate/verify settlement parity during engine deployment.

## Authorized scope
- Deployment may package approved reconciliation rules, logic, modules, validation/schema contracts and the application interface.
- Test only logic using **new synthetic/fictitious fixtures**. Synthetic cases may cover SOL waterfall, TDS 0/1/2/3%, SBISA, multiple months, partial payments, credit notes, duplicates, suspense, and GST. No real past financial transactions in tests.
- Preserve all historical invoice, payment, Credit Note, GST, allocation, suspense and financial-report values **exactly as they were**. Do not calculate, recalculate, replay, reprocess, backfill, import, compare financial values, reconcile or modify any earlier/existing records.
- No connection to legacy financial databases, private historical workbooks, bank statements, customer invoice/credit-note exports, or mounted previous financial data during testing or deployment. No automatic startup scanning or migration jobs.
- A future new-payment intake may process *new evidence explicitly submitted after activation and authorized through its own review workflow*; it must not scan or retroactively process past payment/invoice records.

## Technical gates
1. `logic_only_deploy_gate.py` rejects a deployment manifest that authorizes any historical finance reads, calculations, source mounts, backfills, replays, database migrations, automatic old-evidence processing, writes or production traffic changes. The tests use synthetic manifest objects only.
2. This manifest check is **source-level policy validation**, not proof of actual IAM/firewall/runtime isolation. Actual deploy must enforce the same restrictions in infrastructure, startup scripts, service account scopes, and isolated regression tests.
3. Do not claim the currently deployed AWS Workspace supports new evidence intake, or that historical financial values are verified, recalculated or approved.
4. Production release, financial writes, schema changes, or any later permission to process existing records require separately explicit owner instruction. **No such permission is granted here.**

**DEPLOY_RULES_ONLY=YES; TEST_SYNTHETIC_ONLY=YES; HISTORICAL_DATA_COMPUTATION=PROHIBITED; PREVIOUS_ALLOCATIONS=IMMUTABLE; AWS_DEPLOYMENT_PERFORMED=NO.**
