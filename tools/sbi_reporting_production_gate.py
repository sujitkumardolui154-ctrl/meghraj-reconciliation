"""Fail-closed eligibility check for AUTOMATED REPORTING-ONLY Cloud Run promotion.

This never deploys or updates financial data. The evidence must be externally
prepared by independent QA in a private GCS bucket; CI pins its exact SHA256
through a protected GitHub environment variable. No source-controlled test
result, issue label, or synthetic PASS is sufficient for production.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
REV_RE = re.compile(r"^sbi-dashboard-[a-z0-9-]{5,55}$")
REQUIRED_TRUE = (
    "independent_qa_approved",
    "financial_execution_restricted",
    "live_database_writes_disabled",
    "import_receipts_complete",
    "report_snapshot_fresh",
    "sbi_header_contract_verified",
    "financial_contract_tests_passed",
    "source_tests_passed",
    "private_canary_iam_verified",
    "authenticated_viewer_http_passed",
    "unauthorized_viewer_http_denied",
    "anonymous_http_denied",
    "revoked_session_http_denied",
    "expired_session_http_denied",
    "logout_invalidation_http_passed",
    "csv_export_http_passed",
    "rollback_rehearsal_passed",
    "cloud_run_candidate_ready",
)


def validate_evidence(raw: bytes, expected_sha: str, commit: str,
                      now: dt.datetime | None = None) -> str:
    if not SHA_RE.fullmatch(expected_sha):
        raise ValueError("PROTECTED_EVIDENCE_DIGEST_MISSING")
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("EVIDENCE_DIGEST_MISMATCH")
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("INVALID_GIT_SHA")
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("INVALID_EVIDENCE_JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("INVALID_EVIDENCE_OBJECT")
    if data.get("release_class") != "REPORTING_ONLY":
        raise ValueError("FINANCIAL_PRODUCTION_NOT_AUTHORIZED")
    if data.get("project") != "meghraj-reconciliation":
        raise ValueError("WRONG_GCP_PROJECT")
    if data.get("region") != "asia-south1" or data.get("service") != "sbi-dashboard":
        raise ValueError("WRONG_TARGET_SERVICE")
    if data.get("source_sha") != commit or data.get("qa_source_sha") != commit:
        raise ValueError("EVIDENCE_NOT_BOUND_TO_SOURCE")
    if data.get("release_policy") != "AUTO_AFTER_ALL_GATES":
        raise ValueError("AUTOMATIC_PRODUCTION_AUTHORIZATION_MISSING")
    if data.get("release_review_status") != "APPROVED":
        raise ValueError("RELEASE_REVIEW_PENDING")
    if type(data.get("qa_workflow_run_id")) is not int or data["qa_workflow_run_id"] <= 0:
        raise ValueError("INDEPENDENT_QA_RUN_NOT_IDENTIFIED")
    if not isinstance(data.get("independent_qa_reviewer"), str) or not (
        3 <= len(data["independent_qa_reviewer"].strip()) <= 200
    ):
        raise ValueError("INDEPENDENT_QA_REVIEWER_NOT_IDENTIFIED")
    for name in REQUIRED_TRUE:
        if data.get(name) is not True:
            raise ValueError("MANDATORY_PRODUCTION_GATE_UNVERIFIED:" + name)
    for name in ("report_snapshot_sha256", "baseline_dataset_sha256",
                 "approved_header_contract_sha256"):
        if not SHA_RE.fullmatch(str(data.get(name, ""))):
            raise ValueError("DATASET_OR_CONTRACT_DIGEST_MISSING:" + name)
    revision = data.get("candidate_revision", "")
    if not isinstance(revision, str) or not REV_RE.fullmatch(revision):
        raise ValueError("CANDIDATE_REVISION_INVALID")
    if data.get("tested_candidate_revision") != revision:
        raise ValueError("REAL_HTTP_QA_NOT_BOUND_TO_CANDIDATE")

    def instant(value):
        if not isinstance(value, str):
            raise ValueError("EVIDENCE_TIMESTAMP_MISSING")
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("INVALID_EVIDENCE_TIMESTAMP") from exc
        if parsed.tzinfo is None:
            raise ValueError("EVIDENCE_TIMESTAMP_MISSING_TIMEZONE")
        return parsed.astimezone(dt.timezone.utc)

    issued = instant(data.get("approved_at_utc"))
    expires = instant(data.get("expires_at_utc"))
    now = now or dt.datetime.now(dt.timezone.utc)
    if not (issued <= now < expires and
            dt.timedelta(0) < expires - issued <= dt.timedelta(hours=72)):
        raise ValueError("EVIDENCE_STALE_OR_NOT_YET_VALID")
    return revision


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--output", required=True,
                   help="GitHub job output path (append only)")
    args = p.parse_args()
    revision = validate_evidence(
        Path(args.evidence).read_bytes(), args.sha256, args.commit
    )
    with open(args.output, "a", encoding="utf-8") as fp:
        fp.write("candidate_revision=" + revision + "\n")
    print("REPORTING_ONLY_RELEASE_EVIDENCE=VERIFIED")
    print("CANDIDATE_REVISION=" + revision)


if __name__ == "__main__":
    main()
