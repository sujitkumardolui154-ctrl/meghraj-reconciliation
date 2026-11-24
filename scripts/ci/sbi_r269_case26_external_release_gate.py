"""Case 2.6 release-evidence register. Fail closed; no self-attested approvals.

No local JSON, callback, SHA256 hash or caller booleans can grant financial
permissions. Release requires separately authenticated external evidence and
a distinct authorized deploy action not implemented here.
"""
from dataclasses import dataclass
import re
from sbi_r269_case26_method_coverage_rehearsal import STAGE as METHOD_STAGE

STAGE="R269_CASE26_EXTERNAL_FINANCE_RELEASE_GATE_BLOCKED"
GATES=(
    "ORIGINAL_PRIVATE_XLSX_SHA_AND_CUSTODY",
    "LATEST_OWNER_APPROVED_SOL_MASTER_AND_ALIAS_AUTHORITY",
    "COMPLETE_SIGNED_V251_V239_RULEBOOK_AND_EXECUTABLE_SOURCE",
    "REAL_SBI_UTR_AND_BANK_EVENT_UNIQUENESS",
    "SAME_UPLOAD_INVOICE_OUTSTANDING_AND_PRIOR_K_S_PROTECTION",
    "INDEPENDENT_TDS_GST_CREDIT_NOTE_ACCOUNTING",
    "COMPLETE_SAME_SOL_DNM_SBISA_CROSS_SOL_WATERFALL_PARITY",
    "REAL_INDEPENDENT_ROW_BY_ROW_ALLOCATION_ORACLE",
    "V218_ORIGINAL_EXCEL_WRITER_AND_53_COLUMN_VALUE_PARITY",
    "REAL_FIREBASE_ROLES_SIGNED_IN_AUTHORIZED_DENIED_E2E",
    "REAL_STAGING_DATABASE_ATOMIC_ROLLBACK_AND_RESTORE",
    "SIGNED_FINANCE_SECURITY_OWNER_PRODUCTION_RELEASE",
)


class FinanceReleaseRefusal(ValueError):
    pass


@dataclass(frozen=True)
class ExternalEvidenceDeclaration:
    gate:str
    reference_id:str
    sha256:str
    declared_status:str="PRESENT_UNVERIFIED"


def review_release_readiness(method_rehearsal,external_evidence=(), *,
                             financial_apply="LOCKED"):
    if financial_apply!="LOCKED":
        raise FinanceReleaseRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if type(method_rehearsal) is not dict or not (
        method_rehearsal.get("stage")==METHOD_STAGE
        and method_rehearsal.get("financial_apply_locked") is True
        and method_rehearsal.get("real_database_writes")==0
        and method_rehearsal.get("real_bank_allocations")==0
        and method_rehearsal.get("final_payment_status") is None
        and method_rehearsal.get("full_v251_v239_certified") is False
        and method_rehearsal.get("production_release_authorized") is False
        and method_rehearsal.get("method_oracle_cash_conserved") is True
        and method_rehearsal.get("one_upload_option_b") is True
    ):
        raise FinanceReleaseRefusal("UNSAFE_OR_FORGED_METHOD_REHEARSAL")
    if type(external_evidence) is not tuple:
        raise FinanceReleaseRefusal("IMMUTABLE_EXTERNAL_EVIDENCE_DECLARATIONS_REQUIRED")
    declarations={}
    for e in external_evidence:
        if (type(e) is not ExternalEvidenceDeclaration
                or e.gate not in GATES or e.gate in declarations
                or type(e.reference_id) is not str
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}",e.reference_id)
                or type(e.sha256) is not str
                or not re.fullmatch(r"[a-f0-9]{64}",e.sha256)
                or e.declared_status not in ("PRESENT_UNVERIFIED","REVIEW_REQUESTED")):
            raise FinanceReleaseRefusal("UNVERIFIED_OR_FORGED_EXTERNAL_RELEASE_EVIDENCE")
        declarations[e.gate]=e
    return {
        "stage":STAGE,
        "upload_id":method_rehearsal["upload_id"],
        "method_development_rehearsal_completed":True,
        "real_original_source_or_bank_verified":False,
        "verified_external_evidence_gate_count":0,
        "required_independent_external_gate_count":len(GATES),
        "gates":tuple({
            "gate":gate,
            "status":"PRESENT_BUT_UNAUTHENTICATED" if gate in declarations
                 else "BLOCKED_EXTERNAL_EVIDENCE",
        } for gate in GATES),
        "external_evidence_caller_declarations_only":len(declarations),
        "financial_apply_locked":True,
        "real_financial_allocations":0,
        "real_database_writes":0,
        "real_v218_writer_authorized":False,
        "real_payment_status_assignment_authorized":False,
        "full_v251_v239_financial_certification":False,
        "production_release_authorized":False,
    }
