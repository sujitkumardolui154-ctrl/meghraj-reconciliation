# SBI financial integration phase 1 — metadata attestation only

## Current scope

This implementation prepares a controlled live Firestore read-only metadata
check. It does not deploy or connect the AWS gateway, enable report data,
access invoice rows, reconcile payments, install credentials, change IAM,
modify headers, or permit financial writes.

The AWS report gateway from PR #37 stays isolated, with /readyz 503 and
protected report routes unavailable. Its Dockerfile and internal-only network
are unchanged. Do not weaken network isolation to reach Firestore.

## Approved one-document read

File: staging/aws_backend_readonly/live_financial_metadata_probe.py

The probe uses Application Default Credentials in a separately approved
GCP operator environment and makes exactly one Firestore document GET:

  dashboard_report_datasets/<reviewed-source-sha256>-report-v1

For the existing frozen report source, it validates READY status,
the original source SHA, 14,374 baseline rows, 2,430 unpaid rows,
unpaid classification basis, original-columns READY, 53 columns,
14,374 original-column rows, and the exact ordered 53-column header
contract in backend_source/invoice_import_contract.json.

Duplicate header text is kept at its original position. The separate
34-column source projection is not changed or re-approved.

No invoice values, source rows, customers, metadata payloads, exception text
or credentials are printed. A PASS means metadata only; it does not
certify report values or prove the AWS service is connected.

## Operator commands

From the reviewed repository on an isolated trusted machine, default
dry run never contacts the cloud:

    python staging/aws_backend_readonly/live_financial_metadata_probe.py

After independent IAM and identity approval, run in a private GCP
environment with narrowly authorized read-only Application Default
Credentials, not a downloaded service account key:

    python -m pip install "google-cloud-firestore>=2.20,<3"
    python staging/aws_backend_readonly/live_financial_metadata_probe.py --live-read-only-metadata

Expected statuses: DRY_RUN_NO_DATABASE_ACCESS, PASS_METADATA_ONLY or BLOCKED.
A BLOCKED result must not be bypassed. Never put credentials into GitHub,
chat, Docker build arguments, CI logs or files in this public repository.

A broad Firestore viewer role may read much more data than this diagnostic
needs. If access cannot be restricted appropriately, do not issue broad
credentials; first design a separately restricted approved report dataset
or verified read-only proxy.

## Remaining release gates

1. Provision trusted read-only identity and secure egress separately,
   with no AWS production traffic changes.
2. Confirm the exact source dataset and original approved header contract.
3. Validate actual report row values and parity independently against
   approved source evidence, including outstanding duplicates and conflicts.
4. Prove authentication, access control, auditability and rollback.
5. Obtain independent financial release approval before enabling report
   exports. Financial execution, imports, settlement and writes remain off.

GitHub synthetic tests use mock data and cannot establish live connectivity.
No change to the financial database or AWS service is made by this PR.
