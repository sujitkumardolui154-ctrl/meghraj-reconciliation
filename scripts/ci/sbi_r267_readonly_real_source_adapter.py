"""R26.7 read-only, SHA-pinned SBI source-to-review-planner adapter.

Uses stdlib ZIP/XML and R26.6 workbook integrity scan only. No Excel writes,
database, API, upload or credentials. Invalid rows are quarantined, not
converted into matches. Master parsing loads ONLY explicit official SOL/text
names: aliases, numeric SOLs and missing master IDs are NEVER inferred.
Source bytes/financial values may be private; never upload outputs to CI.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime,timedelta
from decimal import Decimal,InvalidOperation
from hashlib import sha256
import re

from sbi_r266_readonly_real_source_population_gate import (
    _ReadOnlyXlsx,scan_readonly_source,R266Refusal,
)
from sbi_r267_readonly_real_candidate_engine import (
    InvoiceInput,BankInput, FinancialReviewRefusal,
)

M_ABBR=("JAN","FEB","MAR","APR","MAY","JUN","JUL",
        "AUG","SEP","OCT","NOV","DEC")
M_NUM={x:i for i,x in enumerate(M_ABBR,1)}
MONTH_PAT=r"(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|NOV(?:EMBER)?|DEC(?:EMBER)?|SEPT)"
CENT=Decimal("0.01")
SOL_RE=re.compile(r"[0-9]{1,12}\Z")


def excel_date(value):
    if value is None or value=="":
        return None
    try:
        n=Decimal(str(value))
        if n.is_finite() and n==n.to_integral_value() and 15000<n<73050:
            return date(1899,12,30)+timedelta(days=int(n))
    except (ValueError,InvalidOperation):
        pass
    if not isinstance(value,str):
        return None
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%m/%d/%Y"):
        try:return datetime.strptime(value.strip(),fmt).date()
        except ValueError:pass
    return None


def _month_num(value):
    return M_NUM.get(value[:3].upper()) if isinstance(value,str) else None


def service_months(raw):
    """Evidence only: never infer period from invoice/bank posting date."""
    serial=excel_date(raw)
    if serial:return (serial.strftime("%Y-%m"),)
    if not isinstance(raw,str) or not raw.strip():return ()
    s=re.sub(r"\s+"," ",raw.upper().strip())
    periods=set()
    # MAR-MAY 2026, MARCH TO MAY2026, MAR TO MAY-2026
    ranges=re.finditer(
        rf"\b({MONTH_PAT})\s*(?:TO|THROUGH|THRU|UNTIL|TILL|[-–])\s*"
        rf"({MONTH_PAT})\s*(20[0-9]{{2}})\b",s,re.I)
    for m in ranges:
        a,b=_month_num(m.group(1)),_month_num(m.group(2))
        if a is not None and b is not None and a<=b:
            periods.update(f"{m.group(3)}-{n:02d}" for n in range(a,b+1))
    # Month with YYYY, or two-digit 20XX such as AUG-26, SEP 23
    for m in re.finditer(rf"\b({MONTH_PAT})[\s.\-/]*((?:20)?[0-9]{{2}})\b",s,re.I):
        month=_month_num(m.group(1))
        year=int(m.group(2))
        if year<100:year+=2000
        if month is not None and 2017<=year<=2035:
            periods.add(f"{year}-{month:02d}")
    # Numeric month/year: 08-2026 / 08/26 (not date 20-08-2026)
    for m in re.finditer(r"(?<![0-9])(?:0?[1-9]|1[0-2])[-/](?:20[0-9]{2}|[0-9]{2})(?![0-9])",s):
        month,year=m.group(0).replace("/","-").split("-")
        year=int(year);year=year+2000 if year<100 else year
        if 2017<=year<=2035:periods.add(f"{year}-{int(month):02d}")
    # ISO year-month
    for m in re.finditer(r"\b(20[0-9]{2})[-/](0[1-9]|1[0-2])\b",s):
        periods.add(f"{m.group(1)}-{m.group(2)}")
    return tuple(sorted(periods))


def _raw(row,idx):
    return row.get(idx,(None,None,False))[0]


def _type(row,idx):
    return row.get(idx,(None,None,False))[1]


def _money(raw):
    if raw is None or str(raw).strip()=="":
        return None
    try:
        n=Decimal(str(raw))
        return (str(n.quantize(CENT)) if n.is_finite() else None)
    except (InvalidOperation,ValueError):
        return None


@dataclass(frozen=True)
class PrivateSourceSnapshot:
    invoices:tuple[InvoiceInput,...]
    payments:tuple[BankInput,...]
    master_pairs:tuple[tuple[str,str],...]
    review_only_hold_codes:tuple[tuple[str,int,str],...]
    source_sha256:str
    master_sha256:str
    selected_master_invalid_sol_rows:int
    source_preflight:dict


def read_private_snapshots(
    source_bytes,master_bytes,*,source_sha256,master_sha256,
    financial_apply="LOCKED",
):
    if financial_apply!="LOCKED":
        raise FinancialReviewRefusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if (not isinstance(source_bytes,bytes) or not isinstance(master_bytes,bytes)
         or len(master_bytes)>8*1024*1024):
        raise FinancialReviewRefusal("SOURCE_AND_MASTER_BYTES_REQUIRED")
    if sha256(source_bytes).hexdigest()!=source_sha256:
        raise FinancialReviewRefusal("SOURCE_SHA256_MISMATCH")
    if sha256(master_bytes).hexdigest()!=master_sha256:
        raise FinancialReviewRefusal("MASTER_SHA256_MISMATCH")
    preflight=scan_readonly_source(
        source_bytes,expected_sha256=source_sha256,
    )
    s=_ReadOnlyXlsx(source_bytes)
    m=_ReadOnlyXlsx(master_bytes)
    iv=[];pay=[];pairs=[];holds=[];invalid_master=0
    try:
        if "Clean Branch Master" not in m.sheet_paths:
            raise FinancialReviewRefusal("OFFICIAL_CLEAN_BRANCH_MASTER_MISSING")
        for rowno,row in m.rows("Clean Branch Master",{2,4}):
            if rowno==1:
                if _raw(row,2)!="Official Branch Name" or _raw(row,4)!="SOL ID":
                    raise FinancialReviewRefusal("OFFICIAL_MASTER_HEADER_MISMATCH")
                continue
            code=_raw(row,4);name=_raw(row,2)
            if (not isinstance(code,str) or not SOL_RE.fullmatch(code)
                or not isinstance(name,str) or not name.strip()):
                invalid_master+=1
                holds.append(("MASTER",rowno,"MASTER_SOL_OR_OFFICIAL_NAME_INVALID"))
                continue
            pairs.append((code,name))
        for rowno,row in s.rows("Invoice Details.",{5,6,7,8,10,11,12,13,14,19}):
            if rowno==1:continue
            raw_code=_raw(row,7)
            if _type(row,7) not in ("s","inlineStr","str") or not isinstance(raw_code,str):
                holds.append(("INVOICE",rowno,"NUMERIC_OR_MISSING_SOL_SOURCE_TYPE"))
                continue
            key=_raw(row,10)
            if not isinstance(key,str) or not key.strip():
                holds.append(("INVOICE",rowno,"INVOICE_NO_NOT_TEXT"))
                continue
            values=[_money(_raw(row,c)) for c in (11,12,13,14)]
            if any(x is None for x in values):
                holds.append(("INVOICE",rowno,"INVOICE_CORE_MONEY_NONNUMERIC"))
                continue
            source_date=excel_date(_raw(row,6))
            if source_date is None:
                holds.append(("INVOICE",rowno,"ISSUE_DATE_NOT_PARSABLE"))
                continue
            months=service_months(_raw(row,5))
            if not months:
                holds.append(("INVOICE",rowno,"SERVICE_PERIOD_NOT_VERIFIED"))
                continue
            iv.append(InvoiceInput(
                rowno,key,raw_code,str(_raw(row,8) or ""),source_date,
                months,*values,_raw(row,19),
            ))
        for rowno,row in s.rows("PAYMNENT",{3,4,5,6,7,9,11}):
            if rowno==1:continue
            credit=_money(_raw(row,9))
            if credit is None:
                # Blank/not-numeric rows are not incoming receipts.
                holds.append(("PAYMENT",rowno,"BANK_CREDIT_BLANK_OR_NONNUMERIC"))
                continue
            if Decimal(credit)<=0:
                holds.append(("PAYMENT",rowno,"BANK_CREDIT_NONPOSITIVE"))
                continue
            if _type(row,6) not in ("s","inlineStr","str"):
                holds.append(("PAYMENT",rowno,"BANK_SOL_NOT_TEXT"))
                continue
            posted=excel_date(_raw(row,3)) or excel_date(_raw(row,4))
            if posted is None:
                holds.append(("PAYMENT",rowno,"BANK_POSTING_DATE_UNVERIFIED"))
                continue
            description=_raw(row,5)
            if not isinstance(description,str):
                holds.append(("PAYMENT",rowno,"BANK_NARRATION_NOT_TEXT"))
                continue
            pay.append(BankInput(
                rowno,_raw(row,6),str(_raw(row,7) or ""),
                posted,service_months(description),description,
                credit,_raw(row,11),
            ))
    finally:
        m.close();s.close()
    return PrivateSourceSnapshot(
        tuple(iv),tuple(pay),tuple(pairs),
        tuple(holds),source_sha256,master_sha256,
        invalid_master,preflight,
    )


def sanitized_receipt(snapshot):
    """Never print private invoice references, bank narration or client names."""
    return {
        "stage":"R267_PRIVATE_SOURCE_READONLY_NORMALIZATION",
        "source_sha256":snapshot.source_sha256,
        "master_sha256":snapshot.master_sha256,
        "invoice_records_for_review":len(snapshot.invoices),
        "positive_credit_records_for_review":len(snapshot.payments),
        "official_master_pairs":len(snapshot.master_pairs),
        "master_invalid_identities":snapshot.selected_master_invalid_sol_rows,
        "source_holds_by_kind":{
            kind:sum(1 for k,_,_ in snapshot.review_only_hold_codes if k==kind)
            for kind in ("MASTER","INVOICE","PAYMENT")
        },
        "financial_apply_locked":True,
        "production_database_writes":0,
        "real_bank_allocations":0,
        "output_statuses_not_certified":True,
    }
