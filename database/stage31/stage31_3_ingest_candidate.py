"""Stage 31.3: review-only, exact-paise ingestion candidate. NEVER writes.

This module deliberately lacks DB credentials or INSERT execution. Source rows
must be verified against original Excel before any production ingestion.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from invoice_source_schema import invoice_number, row_layout
from stage31_2_schema_design import SOURCE_COLUMNS, HEADERS

_HEX64=re.compile(r"^[0-9a-f]{64}$")
_MONEY=re.compile(r"^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,2})?$")
_SOL=re.compile(r"^[0-9]{1,12}$")
_INVOICE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,99}$")
_MAX_PAISE=9999999999999999

def rupees_to_paise(value):
    """Exact currency-to-integer conversion, never float or implicit rounding."""
    if not isinstance(value,str) or not _MONEY.fullmatch(value):
        raise ValueError("INVALID_RUPEE_TEXT_EXACT_PRECISION_REQUIRED")
    try:
        amount=Decimal(value)*100
    except InvalidOperation as exc:
        raise ValueError("INVALID_RUPEE_DECIMAL") from exc
    paise=int(amount)
    if Decimal(paise)!=amount or paise>_MAX_PAISE:
        raise ValueError("INVALID_RUPEE_PRECISION_OR_RANGE")
    return paise

def _date(value):
    if not isinstance(value,str):
        raise ValueError("DATE_REQUIRES_TEXT")
    for fmt in ("%Y-%m-%d","%d/%m/%Y"):
        try:
            obj=datetime.strptime(value,fmt).date()
            # Fail on loosely padded or normalized input, require actual exact format.
            if obj.strftime(fmt)==value:
                return obj.isoformat()
        except ValueError:
            pass
    raise ValueError("INVOICE_DATE_FORMAT_REVIEW_REQUIRED")

def _source_key(source_file_sha, sheet, row_index, invoice):
    # Including the source workbook SHA and original row preserves origin.
    raw=json.dumps([source_file_sha,sheet,row_index,invoice],
                   separators=(",",":"),ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()

def build_invoice_review_candidate(row, source_file_sha256, source_sheet,
                                   original_row_number, existing_invoice_numbers=()):
    """Make an *unapproved* candidate from an original source row.

    No automatic branch/client-name resolution or final DB insert columns;
    'source_row_id' is a target FK and must be resolved in a later QA stage.
    """
    if not isinstance(row,dict):
        raise ValueError("INVALID_SOURCE_ROW")
    if (not isinstance(source_file_sha256,str)
        or not _HEX64.fullmatch(source_file_sha256)):
        raise ValueError("SOURCE_WORKBOOK_SHA256_REQUIRED")
    if not isinstance(source_sheet,str) or source_sheet!="Invoice Details.":
        raise ValueError("VERIFIED_ORIGINAL_INVOICE_SHEET_REQUIRED")
    if (type(original_row_number) is not int or original_row_number<2
        or row.get("source_row")!=original_row_number):
        raise ValueError("ORIGINAL_SOURCE_ROW_MISMATCH")
    width,_,_,_,headers=row_layout(row)
    if row.get("original_headers")!=list(HEADERS[width]):
        raise ValueError("ORIGINAL_HEADER_PARITY_REQUIRED")
    values=row["original_values"]
    columns=SOURCE_COLUMNS[width]
    number=invoice_number(row)
    if not _INVOICE.fullmatch(number) or number!=number.strip():
        raise ValueError("INVOICE_NO_INVALID_EXACT_MATCH")
    if number in set(existing_invoice_numbers):
        raise ValueError("EXISTING_INVOICE_MUST_NOT_BE_OVERWRITTEN")
    errors=[]
    paise={}
    for source_key,target in (
        ("taxable_amount","taxable_paise"),
        ("cgst","cgst_paise"),
        ("sgst","sgst_paise"),
        ("total_bill_amount","gross_paise"),
    ):
        try:
            paise[target]=rupees_to_paise(values[columns[source_key]])
        except ValueError:
            errors.append("UNVERIFIED_"+source_key.upper())
            paise[target]=None
    if all(v is not None for v in paise.values()) and (
        paise["taxable_paise"]+paise["cgst_paise"]+paise["sgst_paise"] !=
        paise["gross_paise"]
    ):
        errors.append("GROSS_NOT_EQUAL_TAXABLE_PLUS_GST_REQUIRE_SOURCE_REVIEW")
    try:
        invoice_date=_date(values[columns["invoice_date"]])
    except ValueError:
        invoice_date=None
        errors.append("INVOICE_DATE_REVIEW_REQUIRED")
    source_sol=values[columns["branch_code_primary"]]
    sol_id=source_sol if _SOL.fullmatch(source_sol) else None
    if sol_id is None:
        errors.append("SOL_SOURCE_NOT_VERIFIED")
    if "branch_code_secondary" in columns:
        alternate=values[columns["branch_code_secondary"]]
        if alternate and alternate!=source_sol:
            errors.append("CONFLICTING_OR_SECONDARY_ORIGINAL_BRANCH_CODE_REVIEW")
    client_a,client_b=values[0],values[7]
    if not client_a.strip() or not client_b.strip() or client_a!=client_b:
        errors.append("TWO_CLIENT_NAME_COLUMNS_REQUIRE_VERIFICATION")
    service_period=values[columns["month"]]
    if not service_period.strip():
        errors.append("SERVICE_PERIOD_UNVERIFIED")
    # Not mapped into write schema; branch_id/client_name are independently
    # verified requirements; the duplicate Client Name fields are kept in the
    # original source evidence, never silently selected.
    errors.append("BRANCH_ID_AND_VERIFIED_CLIENT_NAME_MAPPING_NOT_APPROVED")
    errors.append("SOURCE_ROW_FOREIGN_KEY_RECEIPT_NOT_INTEGRATED")
    return {
        "status":"REVIEW_REQUIRED_NO_PRODUCTION_WRITES",
        "source_column_count":width,
        "source_identity_fingerprint":_source_key(
            source_file_sha256,source_sheet,original_row_number,number),
        "candidate_fields":{
            "invoice_number":number,
            "invoice_date":invoice_date,
            "service_period_original":service_period,
            "sol_id":sol_id,
            **paise,
        },
        "review_flags":sorted(set(errors)),
        "financial_engine_enabled":False,
        "production_write_authorized":False,
    }

def preview_invoice_batch(rows, source_file_sha256, source_sheet,
                          existing_invoice_numbers=()):
    """All-or-nothing batch preview of original rows; duplicate IDs block both."""
    if not isinstance(rows,(list,tuple)) or len(rows)>20000:
        raise ValueError("SOURCE_BATCH_TOO_LARGE")
    ids=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_SOURCE_ROW")
        ids.append(invoice_number(row))
    duplicate_ids={x for x in ids if ids.count(x)>1}
    if duplicate_ids:
        raise ValueError("DUPLICATE_IN_UPLOADED_SOURCE_REJECT_WHOLE_BATCH")
    candidate=[]
    for row in rows:
        candidate.append(build_invoice_review_candidate(
            row,source_file_sha256,source_sheet,row["source_row"],
            existing_invoice_numbers=existing_invoice_numbers))
    return {
        "status":"REVIEW_REQUIRED_NO_PRODUCTION_WRITES",
        "total":len(candidate),
        "candidates":candidate,
        "production_write_authorized":False,
    }
