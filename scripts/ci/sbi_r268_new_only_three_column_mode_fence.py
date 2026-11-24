"""R26.8 separation fence: historical full Excel QA vs NEW-ONLY 3-column intake.

Both are strictly read-only until bank identity/UTR/date, activation cutoff,
full engine/Excel writer and signed Finance QA are proved. This is an intake
policy guard, not a financial engine or settlement pathway.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from hashlib import sha256
import re

MODES=("HISTORICAL_XLSX_READONLY","NEW_ONLY_THREE_COLUMN_REVIEW")
NEW_HEADERS=("Description","SOL ID","Credit Amount")
HISTORICAL_SHEETS=("Invoice Details.","PAYMNENT")
SOURCE_HASH=re.compile(r"[0-9a-f]{64}\Z")
SOL=re.compile(r"[0-9]{1,12}\Z")
STAGE="R268_NEW_ONLY_AND_HISTORICAL_SOURCE_PROVENANCE_FENCE"


class R268Refusal(ValueError):
    """Constant fail-closed error code only."""


def _hash(s):
    if not isinstance(s,str) or not SOURCE_HASH.fullmatch(s):
        raise R268Refusal("EXACT_SOURCE_SHA_REQUIRED")
    return s


def _parse_cutoff(s):
    if s is None:return None
    if not isinstance(s,str):
        raise R268Refusal("NEW_ONLY_ACTIVATION_CUTOFF_NOT_TEXT")
    try:
        d=datetime.fromisoformat(s)
    except ValueError:
        raise R268Refusal("NEW_ONLY_ACTIVATION_CUTOFF_INVALID")
    if d.tzinfo is None or d.utcoffset()!=timedelta(hours=5,minutes=30):
        raise R268Refusal("NEW_ONLY_ACTIVATION_CUTOFF_NOT_IST")
    return d.isoformat()


def audit_intake_mode(mode,header_names,*,source_sha256,cutoff_ist=None,
                      declared_bank_utr_present=False,
                      bank_origin_independently_authenticated=False,
                      financial_apply="LOCKED"):
    if financial_apply!="LOCKED":
        raise R268Refusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    _hash(source_sha256)
    if mode not in MODES:
        raise R268Refusal("EXPLICIT_INTAKE_MODE_REQUIRED")
    if not isinstance(header_names,(tuple,list)):
        raise R268Refusal("SCHEMA_HEADERS_REQUIRED")
    if mode=="HISTORICAL_XLSX_READONLY":
        if tuple(header_names)!=HISTORICAL_SHEETS:
            raise R268Refusal("HISTORICAL_SHEET_IDENTITY_MISMATCH")
        if cutoff_ist is not None:
            raise R268Refusal("HISTORICAL_INPUT_CANNOT_SET_NEW_ONLY_CUTOFF")
        return {
            "stage":STAGE,"mode":mode,
            "source_sha256":source_sha256,
            "real_historical_payment_allocation_authorized":False,
            "new_only_bank_origin_proved":False,
            "cutoff_set":False,
            "financial_statuses_created":0,
            "financial_apply_locked":True,
            "production_database_writes":0,
            "release_authorized":False,
        }
    if tuple(header_names)!=NEW_HEADERS:
        raise R268Refusal("NEW_ONLY_EXACT_THREE_COLUMN_CONTRACT_REQUIRED")
    if type(declared_bank_utr_present) is not bool or type(bank_origin_independently_authenticated) is not bool:
        raise R268Refusal("BANK_EVIDENCE_BOOLEAN_REQUIRED")
    cutoff=_parse_cutoff(cutoff_ist)
    return {
        "stage":STAGE,"mode":mode,
        "source_sha256":source_sha256,
        "new_only_cutoff_ist":cutoff,
        "cutoff_set":cutoff is not None,
        "bank_utr_column_in_upload":False,
        "bank_date_column_in_upload":False,
        "declared_external_utr_evidence":declared_bank_utr_present,
        "declared_external_bank_auth_evidence":bank_origin_independently_authenticated,
        "independently_verified_bank_origin":False,
        "new_only_rows_eligible_for_financial_settlement":0,
        "real_historical_payment_allocation_authorized":False,
        "financial_statuses_created":0,
        "financial_apply_locked":True,
        "production_database_writes":0,
        "release_authorized":False,
    }


def review_new_only_rows(rows,*,source_sha256,financial_apply="LOCKED"):
    """Three original columns, strict text SOL, cash; review-only no join to ledgers."""
    if financial_apply!="LOCKED":
        raise R268Refusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    _hash(source_sha256)
    if type(rows) not in (list,tuple) or len(rows)>50000:
        raise R268Refusal("THREE_COLUMN_SOURCE_SIZE_OR_SCHEMA_INVALID")
    reasons=[]
    reviewed=0
    for index,row in enumerate(rows,2):
        if type(row) not in (tuple,list) or len(row)!=3:
            reasons.append((index,"REQUIRES_EXACT_THREE_FIELDS"))
            continue
        desc,sol,credit=row
        if not isinstance(desc,str) or not desc.strip():
            reasons.append((index,"DESCRIPTION_REQUIRED"));continue
        if not isinstance(sol,str) or not SOL.fullmatch(sol):
            reasons.append((index,"SOL_MUST_BE_EXACT_TEXT"));continue
        if isinstance(credit,bool) or isinstance(credit,float) or credit is None:
            reasons.append((index,"CREDIT_MUST_BE_EXACT_DECIMAL"));continue
        try:
            val=Decimal(str(credit))
        except (ValueError,InvalidOperation):
            reasons.append((index,"CREDIT_NOT_NUMERIC"));continue
        if not val.is_finite() or val<=0:
            reasons.append((index,"CREDIT_NONPOSITIVE"));continue
        if val!=val.quantize(Decimal("0.01")):
            reasons.append((index,"CREDIT_SUBPAISE_UNVERIFIED"));continue
        reviewed+=1
    return {
        "stage":STAGE,
        "mode":"NEW_ONLY_THREE_COLUMN_REVIEW",
        "source_sha256":source_sha256,
        "rows_seen":len(rows),
        "format_candidates_only":reviewed,
        "hold_reasons":tuple(reasons),
        "authenticated_bank_transaction_date_available":False,
        "authenticated_utr_unique_event_available":False,
        "new_only_activation_cutoff_not_evidenced_here":True,
        "reconciliation_or_older_status_copy_permitted":False,
        "financial_statuses_created":0,
        "real_bank_credits_allocated":0,
        "financial_apply_locked":True,
        "production_database_writes":0,
        "release_authorized":False,
    }
