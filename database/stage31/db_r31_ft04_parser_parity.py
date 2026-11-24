"""R31 combined adapter: preserve original application's duplicate-row decisions.

FT-04's original classify_payment_rows isolates rows when the full workbook
has review flags. A second duplicate becomes "valid" when parsed alone, so
aggregate counts diverge. This adapter retains the exact first-seen sequence
of normalized (Description, SOL ID, Credit Amount) from original per-row
parser previews, including invalid rows, then checks FULL-WORKBOOK count
and accepted credit parity. The FT-04 low-level XLSX extractor and one-row
source reconstruction remain authoritative; no business rules invented.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re

MAX_INDIVIDUAL_REVIEWS = 2000
_SAFE = re.compile(r"[A-Z0-9_:-]{3,100}\Z")


class RowParityReviewRequired(ValueError):
    pass


def require(ok,code):
    if not ok:
        raise RowParityReviewRequired(code)


def _paise(text):
    try:
        n=Decimal(str(text))*100
    except (InvalidOperation,ValueError):
        return None
    if not n.is_finite() or n<=0 or n!=n.to_integral_value():
        return None
    return int(n)


def classify_exact_ft04_rows(payload, original_parser, ft04):
    """Return existing FT-04 accepted/review tuple shape without fake matches.

    ft04: exact SHA-pinned module (low-level _all_source_rows,
    _single_row_xlsx, _credit_paise). Source-only; no database access.
    """
    require(type(payload) is bytes and callable(original_parser),
            "ORIGINAL_SOURCE_PARSER_REQUIRED")
    full=original_parser(payload)
    rows=ft04._all_source_rows(payload)
    require(type(full) is dict and type(rows) is list and rows and
            full.get("source_rows")==len(rows),"FULL_SOURCE_ROW_COUNT_DISAGREES")
    partial=bool(full.get("review_rows"))
    require(not(partial and len(rows)>MAX_INDIVIDUAL_REVIEWS),
            "INDIVIDUAL_ROW_PARSER_LIMIT")
    eligible=[]
    reviewed=[]
    normalized_seen=set()
    accepted_paise=0
    for number, row, raw_error in rows:
        reason=raw_error
        try:
            single=original_parser(ft04._single_row_xlsx(payload,number))
            require(type(single) is dict and single.get("source_rows")==1,
                    "SINGLE_ROW_RECONSTRUCTION_UNVERIFIED")
            preview=single.get("preview",[])
            require(type(preview) is list and len(preview)==1,
                    "SINGLE_ROW_NORMALIZATION_UNVERIFIED")
            one=preview[0]
            require(type(one) is dict and
                    all(type(one.get(k)) is str for k in
                        ("description","sol_id","credit_amount")),
                    "ORIGINAL_PARSER_PREVIEW_FIELDS_MISSING")
            key=(one["description"],one["sol_id"],one["credit_amount"])
            prior=key in normalized_seen
            normalized_seen.add(key)
            if prior and not reason:
                reason="REPEATED_SOURCE_ROW_REVIEW"
            if single.get("valid_rows")!=1 or single.get("review_rows")!=0:
                flags=one.get("review_flags",[])
                if not reason:
                    reason=(flags[0] if type(flags) is list and flags and
                            type(flags[0]) is str and _SAFE.fullmatch(flags[0])
                            else "ORIGINAL_PARSER_ROW_REVIEW")
        except RowParityReviewRequired:
            raise
        except (ValueError,TypeError,KeyError,InvalidOperation,
                AttributeError,IndexError):
            reason=reason or "ORIGINAL_ROW_RECONSTRUCTION_REVIEW"
        amount=_paise(row.get("Credit Amount") if type(row) is dict else None)
        if amount is None and not reason:
            reason="INVALID_CREDIT_AMOUNT"
        if reason:
            require(type(reason) is str and _SAFE.fullmatch(reason),
                    "UNSAFE_SOURCE_REVIEW_REASON")
            reviewed.append({"source_row":number,"reason":reason})
        else:
            require(type(row) is dict and type(number) is int and number>=2,
                    "FT04_ROW_SOURCE_UNVERIFIED")
            eligible.append((number,row,amount))
            accepted_paise+=amount
    require(len(eligible)==full.get("valid_rows") and
            len(reviewed)==full.get("review_rows"),
            "EXACT_DUPLICATE_ROW_PARSER_COUNT_MISMATCH")
    try:
        reported=Decimal(str(full.get("valid_credit_total")))*100
    except (InvalidOperation,ValueError,TypeError):
        raise RowParityReviewRequired("SOURCE_CREDIT_TOTAL_INVALID") from None
    require(reported.is_finite() and reported==accepted_paise,
            "EXACT_DUPLICATE_ROW_CREDIT_PARITY_MISMATCH")
    return eligible,reviewed
