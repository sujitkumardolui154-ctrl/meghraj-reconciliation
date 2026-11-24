"""SBI Case 1: exact, auditable payment-header normalization for fresh uploads.

The historical bank workbook is a RULE-BUILDING FIXTURE ONLY. Neither matching
its invoice/payment population nor copying historical OK/K-column statuses is
a certification gate. Uploads are interpreted by unambiguous header MEANING,
never by Excel column position. Source bytes and source column references stay
immutable. Normalization only builds a virtual canonical A:K view.

Selected canonical full-bank contract is the owner's approved blank template:
A Description | B Posting Date | C Service Period | D Bank Reference / UTR |
E Bank / Statement Source | F SOL ID | G Client Name | H Debit |
I Credit | J Balance | K Record For Me.
Column L is a reserved source blank. The separate NEW-ONLY three-column upload
is NOT promoted to this full-bank source without the R26.8 provenance gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

APPROVED_PAYMENT_HEADERS = (
    "Description", "Posting Date", "Service Period", "Bank Reference / UTR",
    "Bank / Statement Source", "SOL ID", "Client Name", "Debit", "Credit",
    "Balance", "Record For Me",
)
CORE_HEADERS = ("Description", "SOL ID", "Credit")
THREE_COLUMN_NEW_ONLY = ("Description", "SOL ID", "Credit Amount")
BANK_DATE_REQUIRED_FOR_REAL_APPLY = "Posting Date"
_HEADER_ALIASES = {
    "Description": ("DESCRIPTION", "NARRATION", "TRANSACTION DESCRIPTION",
                    "TRANSACTION NARRATION", "PAYMENT DESCRIPTION"),
    "Posting Date": ("POSTING DATE", "TXN DATE", "TRANSACTION DATE", "BANK DATE"),
    "Service Period": ("SERVICE PERIOD", "SERVICE MONTH", "SERVICE MONTHS"),
    "Bank Reference / UTR": ("BANK REFERENCE UTR", "BANK REFERENCE / UTR",
                             "UTR", "UTR NO", "BANK UTR", "BANK REFERENCE"),
    "Bank / Statement Source": ("BANK STATEMENT SOURCE", "BANK / STATEMENT SOURCE",
                                 "BANK SOURCE", "STATEMENT SOURCE"),
    "SOL ID": ("SOL ID", "SOL", "BRANCH CODE", "BRANCH CODE SOL ID"),
    "Client Name": ("CLIENT NAME", "NAME", "CUSTOMER NAME"),
    "Debit": ("DEBIT", "DEBIT AMOUNT", "DR AMOUNT"),
    "Credit": ("CREDIT", "CREDIT AMOUNT", "CR AMOUNT"),
    "Balance": ("BALANCE", "CLOSING BALANCE"),
    "Record For Me": ("RECORD FOR ME",),
}
_ALIAS_MAP = {alias:canon for canon,aliases in _HEADER_ALIASES.items()
              for alias in aliases}


class HeaderMappingRefusal(ValueError):
    """Stable structural error; do not display private bank data."""


def _normal(raw):
    if not isinstance(raw, str):
        return ""
    s = unicodedata.normalize("NFKC",raw).strip().upper()
    return re.sub(r"[^A-Z0-9]+", " ",s).strip()


@dataclass(frozen=True)
class PaymentHeaderPlan:
    original_header_count: int
    source_positions: tuple[tuple[str, int | None], ...]  # 1-based index
    ignored_headers: tuple[tuple[int, str], ...]
    missing_fields: tuple[str, ...]
    eligible_for_full_bank_import: bool
    financial_apply_locked: bool = True

    def column(self, canonical):
        for name,index in self.source_positions:
            if name == canonical:
                return index
        raise HeaderMappingRefusal("UNKNOWN_CANONICAL_PAYMENT_FIELD")

    def audit(self):
        return {
            "stage":"SBI_CASE1_HEADER_MEANING_MAPPING",
            "source_to_approved_columns":tuple(
                (name,idx) for name,idx in self.source_positions),
            "unmapped_source_header_columns":tuple(idx for idx,_ in self.ignored_headers),
            "missing_approved_fields":self.missing_fields,
            "eligible_for_full_bank_import":self.eligible_for_full_bank_import,
            "records_physically_reordered":False,
            "historical_row_count_parity_required":False,
            "historical_OK_status_copying_permitted":False,
            "financial_apply_locked":True,
            "production_database_writes":0,
        }


def map_payment_headers(headers, *, require_posting_date=False,
                        explicit_mode="FULL_BANK_REVIEW",
                        financial_apply="LOCKED"):
    """Map one header row to canonical 11-column *virtual* bank layout.

    Ambiguous duplicate aliases (e.g., both CREDIT and CREDIT AMOUNT) are
    refused. A third unlabeled column is NEVER silently guessed as Credit.
    Missing source UTR/service month/bank-source stays None, not fabricated.
    """
    if financial_apply != "LOCKED":
        raise HeaderMappingRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if explicit_mode != "FULL_BANK_REVIEW":
        raise HeaderMappingRefusal("FULL_BANK_MODE_ONLY_USE_R268_FOR_NEW_ONLY")
    if type(headers) not in (tuple,list) or not headers or len(headers)>256:
        raise HeaderMappingRefusal("BANK_HEADER_ROW_REQUIRED")
    if tuple(_normal(x) for x in headers if _normal(x)) == tuple(
        _normal(x) for x in THREE_COLUMN_NEW_ONLY
    ):
        raise HeaderMappingRefusal("NEW_ONLY_UPLOAD_REQUIRES_SEPARATE_R268_INTAKE")
    positions = {}
    ignored = []
    for index,header in enumerate(headers,1):
        normalized=_normal(header)
        if not normalized:
            continue
        canonical=_ALIAS_MAP.get(normalized)
        if canonical is None:
            ignored.append((index,str(header)))
            continue
        if canonical in positions:
            raise HeaderMappingRefusal("DUPLICATE_OR_AMBIGUOUS_PAYMENT_HEADER")
        positions[canonical]=index
    missing_critical=[name for name in CORE_HEADERS if name not in positions]
    if missing_critical:
        raise HeaderMappingRefusal("REQUIRED_BANK_HEADER_MISSING")
    if require_posting_date and BANK_DATE_REQUIRED_FOR_REAL_APPLY not in positions:
        raise HeaderMappingRefusal("BANK_POSTING_DATE_HEADER_REQUIRED")
    missing=tuple(name for name in APPROVED_PAYMENT_HEADERS if name not in positions)
    return PaymentHeaderPlan(
        original_header_count=len(headers),
        source_positions=tuple((name,positions.get(name)) for name in APPROVED_PAYMENT_HEADERS),
        ignored_headers=tuple(ignored),
        missing_fields=missing,
        eligible_for_full_bank_import=not missing_critical
            and BANK_DATE_REQUIRED_FOR_REAL_APPLY in positions,
    )


def canonical_payment_row(source_values, mapping):
    """Return A:K approved-order values without altering original source.

    source_values is a 1-based-column-indexed dictionary of raw cell values.
    None for absent canonical fields; NEVER guess posting date, UTR, customer,
    SOL zero padding, transaction source or credit from another column.
    """
    if not isinstance(mapping,PaymentHeaderPlan):
        raise HeaderMappingRefusal("VERIFIED_PAYMENT_HEADER_PLAN_REQUIRED")
    if not isinstance(source_values,dict):
        raise HeaderMappingRefusal("SOURCE_ROW_DICTIONARY_REQUIRED")
    return tuple(source_values.get(mapping.column(name)) if mapping.column(name)
                 is not None else None for name in APPROVED_PAYMENT_HEADERS)
