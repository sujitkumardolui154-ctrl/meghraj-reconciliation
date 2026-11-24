"""Bridge private Clean Branch Master to the GitHub-approved MXP GST v2.7 rules.

The GitHub repository stores matcher CODE and approved aliases but NOT the
complete private master workbook. This adapter never guesses identities,
addresses, or provenance and never makes database writes.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MATCHER = ROOT / "staging" / "mxp-gst" / "matcher.py"


def _load_matcher():
    spec = spec_from_file_location("sbi_approved_mxp_matcher", MATCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError("APPROVED_GITHUB_MATCHER_NOT_AVAILABLE")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_private_master_rows(master_rows, additional_evidence):
    """Return READY/REVIEW rows; no writes and no manufactured addresses.

    master_rows: approved private rows including Official Branch Name,
      SOL ID, Search Aliases.
    additional_evidence: keyed by (official name, SOL) and provided by a
      separately approved private source with verified customer/address data.
    """
    matcher = _load_matcher()
    if not isinstance(master_rows, list) or not isinstance(additional_evidence, dict):
        raise ValueError("PRIVATE_MASTER_AND_EVIDENCE_REQUIRED")
    seen_sol_names = set()
    output = []
    for number, entry in enumerate(master_rows, start=1):
        errors = []
        official = entry.get("Official Branch Name")
        sol = entry.get("SOL ID")
        if not isinstance(official, str) or not official.strip():
            errors.append("OFFICIAL_BRANCH_NAME_MISSING")
        if not isinstance(sol, str) or not re.fullmatch(r"[0-9]{1,6}", sol):
            errors.append("SOL_NOT_TEXT_OR_INVALID")
        if errors:
            output.append({"source_row": number, "status": "REVIEW_REQUIRED",
                           "flags": errors})
            continue
        sol = sol.zfill(5)
        key = (matcher.normalize(official), sol)
        if key in seen_sol_names:
            errors.append("DUPLICATE_OFFICIAL_SOL")
        seen_sol_names.add(key)
        match = matcher.resolve_name(official, master_rows)
        if (match.get("status") not in ("MATCHED", "APPROVED_SPECIFIC")
                or matcher.normalize(match.get("official_name", "")) != key[0]
                or match.get("sol_id") != sol):
            errors.append("GITHUB_APPROVED_MASTER_MISMATCH")
        evidence = additional_evidence.get(key)
        if not isinstance(evidence, dict) or evidence.get("approved") is not True:
            errors.append("PRIVATE_CUSTOMER_EVIDENCE_MISSING")
            evidence = {}
        for required in ("branch_key", "invoice_branch", "invoice_generate_location",
                         "customer_address", "recipient_title", "verified_by"):
            if not isinstance(evidence.get(required), str) or not evidence[required].strip():
                errors.append("MISSING_" + required.upper())
        if evidence.get("client_class") not in ("SBI_BANK", "SBI_FUND"):
            errors.append("CLIENT_CLASS_UNVERIFIED")
        expected_gstin = {
            "SBI_BANK": "19AAACS8577K3ZK",
            "SBI_FUND": "19AAACS7339D1ZB",
        }.get(evidence.get("client_class"))
        if evidence.get("gstin") != expected_gstin:
            errors.append("GSTIN_VERIFICATION_REQUIRED")
        if official.strip().upper() in ("SBI", "STATE BANK OF INDIA", "REVIEW", "MISSING"):
            errors.append("GENERIC_CLIENT_NAME_REJECTED")
        if errors:
            output.append({"source_row": number, "official_name": official,
                           "sol_id": sol, "status": "REVIEW_REQUIRED",
                           "flags": errors})
            continue
        output.append({
            "source_row": number, "status": "READY_FOR_PRIVATE_QA_IMPORT",
            "flags": [],
            "branch": {
                "branch_key": evidence["branch_key"], "client_name": official,
                "invoice_branch": evidence["invoice_branch"],
                "invoice_generate_location": evidence["invoice_generate_location"],
                "original_branch_name": evidence.get("original_branch_name", official),
                "sol_id": sol, "client_class": evidence["client_class"],
                "gstin": evidence["gstin"], "customer_address": evidence["customer_address"],
                "recipient_title": evidence["recipient_title"], "state_code": "19",
                "verified": True, "verified_by": evidence["verified_by"],
            },
        })
    return output
