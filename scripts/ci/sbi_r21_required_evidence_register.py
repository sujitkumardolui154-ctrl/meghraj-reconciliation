"""R21 read-only required-evidence register and non-promotion release gate.

For handover only: no bank, Firebase or AWS data is read, and no real stage
is automatically approved by CI. No production settlement can be unlocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

DATE_IST = "2026-11-24"
RELEASE_LOCK = "FINANCIAL_APPLY_LOCKED"
SPEC = "Master v2.51 / DIL Matrix v2.39"
OUTPUT = "OUT-SCHEMA-V218-001"
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
KNOWN_OLDER_ENGINE_SHA = frozenset({
    "72d5a2249eb576d26b275081e47623c900c01b591d9b20644b876da0050521bf",
    "6e530dd8727607d252626af2fbf5f104fdce61dbb1c49fe1836bcd0d958241f3",
})

# Each gate has a different authority. A claimed success marker in a ZIP,
# Drive filename or Github test run is not proof of any other gate.
GATES = (
    ("FRESH_SOURCE", "Fresh owner-attested original PAYMNENT + Invoice Details. XLSX; new current request provenance"),
    ("APPROVED_SOL_MASTER", "Latest approved SOL master, exact text IDs, alias/conflict review and signed hash"),
    ("COMPLETE_V251_ENGINE", "Exact executable v2.51/v2.39 source, source-tree hash, independent full rule coverage"),
    ("FINANCIAL_LEDGER", "Independent real same-source bank/invoice oracle; global uniqueness, partials, waterfall-last, TDS, DNM, SBISA"),
    ("REAL_V218_WRITER", "Actual signed v2.18 writer with full money/row/formula/status parity, not review-only serializer"),
    ("REAL_AUTH_SESSION", "Authorized sbi-r9-staging signed ID token -> actual SBI Flask session; CSRF/Apply denied"),
    ("REAL_STAGING_POSTGRES", "Authorized isolated real staging PostgreSQL access, readonly/rollback and complete source parity"),
    ("FINANCE_SECURITY_SIGNOFF", "Independent finance/security evidence, rollback approval and explicit user cutover authorization"),
)
REQUIRED_FILES = (
    "scripts/ci/sbi_r15_financial_source_preflight.py",
    "scripts/ci/sbi_r16_master_identity_shadow.py",
    "scripts/ci/sbi_r17_synthetic_financial_shadow.py",
    "scripts/ci/sbi_r18_output_parity_gate.py",
    "scripts/ci/sbi_r19_combined_synthetic_rehearsal.py",
    "scripts/ci/sbi_r20_synthetic_review_writer.py",
    "scripts/ci/sbi_r20_ephemeral_postgres_qa.py",
    "scripts/ci/sbi_r14_real_app_session_readonly.py",
    "docs/SBI_SAME_DAY_HANDOVER_20261124.md",
)

class EvidenceRefusal(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

def refuse(code):
    raise EvidenceRefusal(code)

def _strict_sha(raw):
    return isinstance(raw, str) and SHA_RE.fullmatch(raw) is not None

def inspect_development_tree(root: Path) -> dict:
    """Read and SHA256 only explicitly allowlisted repo files, not user workbooks."""
    if not isinstance(root, Path) or not root.exists() or not root.is_dir():
        refuse("CHECKED_OUT_DEVELOPMENT_TREE_REQUIRED")
    verified = {}
    for relative in REQUIRED_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            refuse("DEVELOPMENT_REFERENCE_MODULE_MISSING")
        content = path.read_bytes()
        if not content or len(content) > 2 * 1024 * 1024:
            refuse("DEVELOPMENT_REFERENCE_FILE_UNEXPECTED_SIZE")
        verified[relative] = sha256(content).hexdigest()
    return verified

def inspect_candidate_receipt(candidate: dict | None) -> dict:
    """A declaration cannot certify an engine. It requires external signoff."""
    if candidate is None:
        return {
            "gate": "COMPLETE_V251_ENGINE",
            "result": "NOT_VERIFIED",
            "reason": "NO_APPROVED_EXECUTABLE_CANDIDATE_SUBMITTED",
            "independent_method_coverage": False,
            "release_eligible": False,
        }
    if type(candidate) is not dict:
        refuse("ENGINE_CANDIDATE_MANIFEST_INVALID")
    sha = candidate.get("sha256")
    if not _strict_sha(sha):
        refuse("ENGINE_CANDIDATE_SHA256_REQUIRED")
    if sha in KNOWN_OLDER_ENGINE_SHA:
        return {
            "gate": "COMPLETE_V251_ENGINE",
            "result": "REJECTED",
            "reason": "RECOVERED_OLDER_REVIEW_OR_PARTIAL_CANDIDATE",
            "independent_method_coverage": False,
            "release_eligible": False,
        }
    if candidate.get("master_version") != "v2.51" or candidate.get("matrix_version") != "v2.39":
        return {
            "gate": "COMPLETE_V251_ENGINE",
            "result": "NOT_VERIFIED",
            "reason": "APPROVED_VERSION_PAIR_NOT_PROVEN",
            "independent_method_coverage": False,
            "release_eligible": False,
        }
    # Even 'approved': true, 'signed': true, 999 QA tests, or a pasted URL
    # are insufficient until a separately authorized verifier checks source.
    return {
        "gate": "COMPLETE_V251_ENGINE",
        "result": "NOT_VERIFIED",
        "reason": "UNTRUSTED_SELF_DECLARATION_NEEDS_INDEPENDENT_AUTHORITY",
        "candidate_sha256": sha,
        "independent_method_coverage": False,
        "release_eligible": False,
    }

def assess_evidence(root: Path, claims=None) -> dict:
    """Aggregate safe code-integrity facts; no release grant in any outcome."""
    # Deliberately accept and ignore untrusted claims. Any release process must
    # separately verify source authenticity, dated user attachment and signoffs.
    if claims is not None and type(claims) is not dict:
        refuse("EVIDENCE_CLAIMS_MUST_BE_OBJECT")
    claims = claims or {}
    verified_files = inspect_development_tree(root)
    engine = inspect_candidate_receipt(claims.get("engine_candidate"))
    reasons = {
        "FRESH_SOURCE": "CURRENT_REQUEST_FFI001_ATTACHMENT_PROVENANCE_REQUIRED",
        "APPROVED_SOL_MASTER": "REFERENCE_MASTER_NOT_OWNER_SIGNED_FOR_RELEASE",
        "COMPLETE_V251_ENGINE": engine["reason"],
        "FINANCIAL_LEDGER": "FULL_REAL_FINANCIAL_ALLOCATION_PARITY_NOT_TESTED",
        "REAL_V218_WRITER": "REAL_WRITER_AND_MONEY_PARITY_NOT_TESTED",
        "REAL_AUTH_SESSION": "R14_REAL_CLOUD_SHELL_TO_FLASK_RECEIPT_MISSING",
        "REAL_STAGING_POSTGRES": "DISPOSABLE_CI_POSTGRES_NOT_REAL_STAGING_DATABASE",
        "FINANCE_SECURITY_SIGNOFF": "NO_AUTHENTICATED_RELEASE_SIGNOFF",
    }
    return {
        "stage": "R21_READONLY_REQUIRED_EVIDENCE_REGISTER",
        "date_ist": DATE_IST,
        "specification": SPEC,
        "approved_output_contract": OUTPUT,
        "source_scope": "VERSIONED_DEVELOPMENT_CODE_ONLY",
        "development_files_sha256": verified_files,
        "synthetic_ci_reference": {
            "tests_passed_reported": 206,
            "evidence_run": "https://github.com/sujitkumardolui154-ctrl/meghraj-reconciliation/actions/runs/45355368414",
            "scope": "SYNTHETIC_AND_DISPOSABLE_POSTGRES_ONLY",
            "financial_method_certification": False,
        },
        "gates": [
            {
                "name": name,
                "required_evidence": required,
                "status": "BLOCKED_EXTERNAL_EVIDENCE",
                "reason": reasons[name],
            }
            for name, required in GATES
        ],
        "engine_provenance_result": engine,
        "required_external_gates_count": len(GATES),
        "signed_finance_release": False,
        "real_bank_allocations": 0,
        "real_financial_database_accessed": False,
        "production_main_deployed": False,
        "financial_apply_locked": True,
        "production_financial_release_ready": False,
        "release_lock": RELEASE_LOCK,
    }

def run(root: Path) -> dict:
    return assess_evidence(root)

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    print(json.dumps(run(root),sort_keys=True,indent=2))
