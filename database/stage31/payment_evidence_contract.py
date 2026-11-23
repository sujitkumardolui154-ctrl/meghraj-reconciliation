"""Stage 31: offline payment evidence validation contract, NO database writes.

The three-column user-approved minimum is only an intake PREVIEW format,
not a sufficient source for financial settlement or definitive idempotency.
Excel PAYMNENT source column I (Credit) must not be inferred from a
different file without an explicit original-header mapping.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

FIXED_PAYMENT_HEADERS = ("Description", "SOL ID", "Credit Amount")
MAX_ROWS = 20000
MAX_TEXT_LENGTH = 2048
SOL_PATTERN = re.compile(r"^[0-9]{1,12}$")
CURRENCY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,2})?$")

def validate_evidence_headers(headers):
    """Exact approved standalone staging-template header order only."""
    if tuple(headers) != FIXED_PAYMENT_HEADERS:
        raise ValueError("PAYMENT_HEADER_MISMATCH_EXPECTED_DESCRIPTION_SOL_ID_CREDIT_AMOUNT")
    return True

def _row(row, index):
    reasons=[]
    if not isinstance(row,(list,tuple)) or len(row)!=3:
        return {"source_row":index,"status":"REJECTED","reasons":["PAYMENT_SOURCE_ROW_WIDTH_MISMATCH"]}
    desc,sol,credit=row
    if not all(isinstance(x,str) for x in row):
        reasons.append("PAYMENT_SOURCE_CELLS_MUST_BE_EXACT_TEXT")
        return {"source_row":index,"status":"REJECTED","reasons":reasons}
    if not desc.strip() or len(desc)>MAX_TEXT_LENGTH or any(ord(x)<32 for x in desc):
        reasons.append("PAYMENT_DESCRIPTION_INVALID")
    if not SOL_PATTERN.fullmatch(sol):
        reasons.append("SOL_ID_MUST_BE_TEXT_DIGITS_PRESERVE_LEADING_ZEROS")
    if not CURRENCY_PATTERN.fullmatch(credit):
        reasons.append("CREDIT_INVALID_EXACT_2_DECIMAL_MAX")
    else:
        try:
            value=Decimal(credit)
            if not value.is_finite() or value <=0:
                reasons.append("CREDIT_MUST_BE_POSITIVE")
        except InvalidOperation:
            reasons.append("CREDIT_INVALID_NUMBER")
    if reasons:
        return {"source_row":index,"status":"REJECTED","reasons":reasons}
    key=json.dumps([desc,sol,str(Decimal(credit).quantize(Decimal(".01")))],
                   separators=(",",":"),ensure_ascii=False)
    digest=hashlib.sha256(key.encode("utf-8")).hexdigest()
    return {"source_row":index,"status":"READY_FOR_SOURCE_REVIEW",
            "evidence_key_sha256":digest,"reasons":[],
            "finance_processed":False}

def preview_payment_rows(headers, rows, first_source_row=2):
    """Check source format without storing amounts, allocating payments or importing.

    A three-column staging file has no transaction date or bank row identity.
    For that reason every accepted row remains REVIEW-ONLY and no DB writer
    is exported. Duplicate evidence fingerprints are rejected for review.
    """
    validate_evidence_headers(headers)
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROWS:
        raise ValueError("PAYMENT_ROW_LIMIT_EXCEEDED")
    results=[_row(row,i+first_source_row) for i,row in enumerate(rows)]
    counts=Counter(x.get("evidence_key_sha256") for x in results
                   if x["status"]=="READY_FOR_SOURCE_REVIEW")
    for result in results:
        key=result.get("evidence_key_sha256")
        if key and counts[key]>1:
            result["status"]="REJECTED"
            result["reasons"]=["DUPLICATE_PAYMENT_EVIDENCE_REQUIRES_ORIGINAL_BANK_ROW"]
            result.pop("evidence_key_sha256",None)
    return {
        "contract":"STAGE31_PAYMENT_EVIDENCE_MINIMUM_V1",
        "status":"PREVIEW_ONLY",
        "headers":list(FIXED_PAYMENT_HEADERS),
        "total":len(results),
        "ready_for_source_review":sum(x["status"]=="READY_FOR_SOURCE_REVIEW" for x in results),
        "rejected":sum(x["status"]=="REJECTED" for x in results),
        "results":results,
        "database_changed":False,
        "financial_engine_enabled":False,
    }
