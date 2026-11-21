"""Fresh SBI reconciliation *proposal* engine — safety-first synthetic build.

Uses approved Master v2.51 / Matrix v2.39 as a behavioral specification,
not as evidence of an authenticated bank source or production approval.
Never opens files, queries a DB, invokes a network, writes settlement status,
or examines historical records. Only fabricated SYNTH- fixture identities.

Most important restriction: financial decisions are NON-AUTHORITATIVE.
Proposed allocations are in-memory amounts to independently review, NOT 'OK'.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

CENTS = Decimal('0.01')
MAX_RECORDS = 2000
MAX_TEXT = 1024
MONEY = re.compile(r'(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?\Z', re.ASCII)
SYNTH_INVOICE = re.compile(r'SYNTH-INV-[A-Z0-9_-]+\Z', re.ASCII)
SYNTH_UTR = re.compile(r'SYNTH-UTR-[A-Z0-9_-]+\Z', re.ASCII)
SOL = re.compile(r'[0-9]{1,12}\Z', re.ASCII)
MONTH = re.compile(r'20[0-9]{2}-(?:0[1-9]|1[0-2])\Z', re.ASCII)
MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
          'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
MONTH_WORDS = '|'.join(('JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE','JULY',
                      'AUGUST','SEPTEMBER','OCTOBER','NOVEMBER','DECEMBER',
                      'JAN','FEB','MAR','APR','JUN','JUL','AUG','SEP','SEPT','OCT','NOV','DEC'))
EXPLICIT_MXP = re.compile(r'(?<![A-Z0-9])MXP\s*[/\-]?\s*[0-9]+(?:[/\-][0-9]+)*(?![A-Z0-9])', re.I)
SYNTH_NARRATION_REF = re.compile(r'(?<![A-Z0-9])SYNTH-INV-[A-Z0-9_-]+(?![A-Z0-9])', re.ASCII)

class EngineBlocked(ValueError):
    """Source contract, authorization or invariant violation: fail closed."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise EngineBlocked(code)


def amount(raw: Any) -> Decimal:
    require(type(raw) is str and MONEY.fullmatch(raw) is not None,
            'DECIMAL_CREDIT_STRING_REQUIRED')
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise EngineBlocked('DECIMAL_CREDIT_INVALID') from exc
    require(value.is_finite() and value >= 0, 'NONNEGATIVE_DECIMAL_REQUIRED')
    return value.quantize(CENTS)


def day(raw: Any) -> date:
    require(type(raw) is str and bool(re.fullmatch(r'20\d{2}-\d{2}-\d{2}',raw)),
            'ISO_DATE_REQUIRED')
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise EngineBlocked('INVALID_ISO_DATE') from exc


def service_months(raw: Any) -> frozenset[str]:
    require(type(raw) is list and 1 <= len(raw) <= 12 and
            all(type(m) is str and MONTH.fullmatch(m) for m in raw) and
            len(set(raw)) == len(raw), 'VERIFIED_SERVICE_MONTHS_REQUIRED')
    return frozenset(raw)


def _year(y: str) -> int:
    num = int(y)
    return (2000 + num if len(y) == 2 else num)


def _month_iter(first: int, year1: int, last: int, year2: int) -> frozenset[str]:
    start, end = year1 * 12 + first - 1, year2 * 12 + last - 1
    require(0 <= end-start <= 11, 'SERVICE_PERIOD_RANGE_REVIEW')
    return frozenset(f'{n//12:04d}-{(n%12)+1:02d}' for n in range(start,end+1))


def narration_period(description: str) -> frozenset[str] | None:
    """Extract one evidenced service period, not a guessed invoice-date month.

    Supported: AUG-26, August 2026, 08-2026, Mar-May 2026.
    Multiple distinct periods cause review. Other prose is not altered.
    """
    require(type(description) is str and 0 < len(description) <= MAX_TEXT,
            'NARRATION_TEXT_REQUIRED')
    up = description.upper()
    matches: list[frozenset[str]] = []
    occupied: list[tuple[int,int]] = []

    # Explicit word ranges, e.g. Mar-May2026 or March to May 2026.
    ranges = re.compile(rf'(?<![A-Z0-9])({MONTH_WORDS})\s*(?:-|TO|THROUGH)\s*({MONTH_WORDS})\s*(20\d{{2}})(?!\d)')
    for match in ranges.finditer(up):
        a, b = MONTHS[match[1][:3]], MONTHS[match[2][:3]]
        endyear = int(match[3]); startyear = endyear - (a > b)
        matches.append(_month_iter(a,startyear,b,endyear))
        occupied.append(match.span())

    # Number-month and named-month singles; do not count tokens within ranges.
    patterns = [
        re.compile(r'(?<![0-9])(?:0?[1-9]|1[0-2])[-/](?:20\d{2}|\d{2})(?!\d)'),
        re.compile(rf'(?<![A-Z0-9])({MONTH_WORDS})\s*[-/ ]\s*(20\d{{2}}|\d{{2}})(?!\d)')
    ]
    for pat in patterns:
        for m in pat.finditer(up):
            if any(m.start() >= lo and m.end() <= hi for lo,hi in occupied):
                continue
            token=m.group(0)
            if pat is patterns[0]:
                mm, yy = re.split('[-/]',token)
                val=f'{_year(yy):04d}-{int(mm):02d}'
            else:
                val=f'{_year(m[2]):04d}-{MONTHS[m[1][:3]]:02d}'
            matches.append(frozenset([val]))
            occupied.append(m.span())

    if len(matches) == 0:
        return None
    require(len(matches) == 1, 'AMBIGUOUS_NARRATION_PERIOD')
    return matches[0]


def _invoice(row: Any, cutoff: date) -> dict:
    require(type(row) is dict and row.get('source_kind')=='SYNTHETIC',
            'REAL_OR_HISTORICAL_INVOICE_FORBIDDEN')
    ident = row.get('invoice_no')
    require(type(ident) is str and SYNTH_INVOICE.fullmatch(ident),
            'SYNTHETIC_INVOICE_ID_REQUIRED')
    sol = row.get('sol_id'); sbisa = row.get('sbisa')
    require(type(sbisa) is bool, 'EXPLICIT_SBISA_MARKER_REQUIRED')
    require(type(sol) is str and (SOL.fullmatch(sol) or (sol=='' and sbisa)),
            'EXACT_TEXT_SOL_REQUIRED')
    client = row.get('client_name')
    require(type(client) is str and bool(client.strip()) and client==client.strip() and len(client)<=160,
            'VERIFIED_CLIENT_ID_REQUIRED')
    require(all(type(row.get(k)) is bool for k in
                ('source_verified','master_verified','protected_prior','credit_note')),
            'SOURCE_BOOLEAN_PROOF_REQUIRED')
    rate = row.get('approved_tds_rate')
    require(type(rate) is int and rate in (0,1,2,3),
            'EXPLICIT_APPROVED_TDS_RATE_REQUIRED')
    taxable = amount(row.get('taxable')); cgst=amount(row.get('cgst'))
    sgst=amount(row.get('sgst')); gross=amount(row.get('gross'))
    require(taxable > 0 and gross > 0 and
            taxable+cgst+sgst==gross, 'INVOICE_GROSS_MISMATCH')
    paid = row.get('original_paid_marker')
    # Any nonblank marker, including numeric zero, must be held, never read as False.
    require(paid is None or type(paid) in (str,int,float,bool),
            'INVALID_PAID_MARKER_TYPE')
    issued = day(row.get('invoice_date'))
    months = service_months(row.get('service_months'))
    tds=(taxable*Decimal(rate)/Decimal(100)).quantize(CENTS,rounding=ROUND_HALF_UP)
    net=gross-tds
    require(net>0,'INVALID_NET_RECEIVABLE')
    if issued < cutoff:
        blocked='PRE_ACTIVATION_INVOICE'
    elif row['protected_prior'] or paid is not None and paid!='':
        blocked='PAID_OR_PROTECTED_SOURCE'
    elif row['credit_note']:
        blocked='CREDIT_NOTE_REVIEW'
    elif not row['source_verified'] or not row['master_verified']:
        blocked='SOURCE_OR_MASTER_NOT_VERIFIED'
    else:
        blocked=None
    return dict(id=ident,sol=sol,sbisa=sbisa,client=client,issued=issued,months=months,
                net=net,tds=tds,rate=rate,blocked=blocked)


def _payment(row: Any, cutoff: date) -> dict:
    require(type(row) is dict and row.get('source_kind')=='SYNTHETIC',
            'REAL_OR_HISTORICAL_PAYMENT_FORBIDDEN')
    ident=row.get('utr');require(type(ident) is str and SYNTH_UTR.fullmatch(ident),
                                'SYNTHETIC_BANK_REFERENCE_REQUIRED')
    sol=row.get('sol_id');sbisa=row.get('sbisa')
    require(type(sbisa) is bool, 'EXPLICIT_SBISA_MARKER_REQUIRED')
    require(type(sol) is str and SOL.fullmatch(sol), 'EXACT_TEXT_SOL_REQUIRED')
    client=row.get('client_name')
    require(type(client) is str and bool(client.strip()) and client==client.strip() and len(client)<=160,
            'VERIFIED_CLIENT_ID_REQUIRED')
    require(type(row.get('source_verified')) is bool and
            type(row.get('bank_reference_verified')) is bool, 'BANK_SOURCE_PROOF_REQUIRED')
    bankdate=day(row.get('bank_date'))
    credit=amount(row.get('credit'))
    require(credit>0,'POSITIVE_BANK_CREDIT_REQUIRED')
    desc=row.get('description')
    if type(desc) is not str or len(desc)>MAX_TEXT or not desc.strip():
        raise EngineBlocked('NARRATION_TEXT_REQUIRED')
    # No real-world MXP reference is accepted as synthetic data.
    require(EXPLICIT_MXP.search(desc) is None, 'HISTORICAL_MXP_REFERENCE_FORBIDDEN')
    period=narration_period(desc)
    explicit=row.get('invoice_refs')
    require(type(explicit) is list and len(explicit)<=16 and
            all(type(r) is str and SYNTH_INVOICE.fullmatch(r) for r in explicit) and
            len(set(explicit))==len(explicit), 'EXPLICIT_SYNTHETIC_INVOICE_REFS_REQUIRED')
    narration_refs=set(SYNTH_NARRATION_REF.findall(desc))
    if bankdate < cutoff:
        blocked='PRE_ACTIVATION_PAYMENT'
    elif not row['source_verified'] or not row['bank_reference_verified']:
        blocked='BANK_PROVENANCE_UNVERIFIED'
    elif narration_refs and set(explicit)!=narration_refs:
        blocked='CONTRADICTORY_OR_UNVERIFIED_INVOICE_NARRATION'
    elif period is None:
        blocked='SERVICE_PERIOD_EVIDENCE_MISSING'
    else:
        blocked=None
    return dict(id=ident,sol=sol,sbisa=sbisa,client=client,day=bankdate,credit=credit,
                period=period,refs=explicit,blocked=blocked)


def _eligible(inv:dict, pay:dict) -> str|None:
    if inv['blocked']: return inv['blocked']
    if inv['sbisa'] != pay['sbisa']: return 'SBISA_IDENTITY_CONFLICT'
    if inv['sol'] != pay['sol']:
        if not (pay['sbisa'] and pay['sol']=='1' and inv['sol']==''):
            return 'CROSS_SOL_FORBIDDEN'
    if inv['client'] != pay['client']: return 'CLIENT_IDENTITY_CONFLICT'
    age=(pay['day']-inv['issued']).days
    if not 0<=age<=180: return 'OUTSIDE_APPROVED_180_DAY_WINDOW'
    if not inv['months'].issubset(pay['period']): return 'CONTRADICTORY_SERVICE_PERIOD'
    return None


def _s(d: Decimal) -> str:
    return f'{d:.2f}'


def evaluate(invoices: list[dict], payments: list[dict], *,
             activation_cutoff: str, synthetic_only: bool=False) -> dict:
    """One all-or-nothing isolated proposal evaluation; no financial writes.

    Strictly rejects any non-synthetic source; each payment is placed into a
    temporary balance ledger ONLY if the whole synthetic payment can fit.
    Automatic matching is limited to a unique exact-net unreferenced candidate;
    DNM-01 near-dominance is REVIEW, never financial OK.
    """
    require(synthetic_only is True, 'SYNTHETIC_MODE_ONLY')
    cutoff=day(activation_cutoff)
    require(type(invoices) is list and type(payments) is list and
            len(invoices)<=MAX_RECORDS and len(payments)<=MAX_RECORDS,
            'RECORD_LIST_OR_CAP_INVALID')
    ins=[_invoice(x,cutoff) for x in invoices]
    pays=[_payment(x,cutoff) for x in payments]
    invcount=Counter(x['id'] for x in ins)
    paycount=Counter(x['id'] for x in pays)
    unique={x['id']:x for x in ins if invcount[x['id']]==1}
    remaining={id_:x['net'] for id_,x in unique.items()}
    proposals:list[dict]=[]; holds:list[dict]=[]

    def hold(pay:dict,reason:str,**kwargs:Any)->None:
        holds.append(dict(payment_id=pay['id'],reason=reason,**kwargs))

    # No actual bank sequence can be inferred from historical ledgers. This
    # deterministic synthetic sequence is only a candidate simulation.
    for p in sorted(pays,key=lambda x:(x['day'],x['id'])):
        if paycount[p['id']]!=1:
            hold(p,'DUPLICATE_BANK_REFERENCE');continue
        if p['blocked']:
            hold(p,p['blocked']);continue
        if p['refs']:
            if any(invcount[ref]>1 for ref in p['refs']):
                hold(p,'DUPLICATE_INVOICE_NUMBER');continue
            if any(ref not in unique for ref in p['refs']):
                hold(p,'INVOICE_REFERENCE_NOT_FOUND');continue
            chosen=[unique[ref] for ref in p['refs']]
        else:
            # Never auto-match on an incomplete same-SOL invoice inventory.
            relevant=lambda x: (x['sol']==p['sol'] or
                 (p['sbisa'] and p['sol']=='1' and x['sol']=='' and x['sbisa']))
            if any(relevant(x) and invcount[x['id']]>1 for x in ins):
                hold(p,'DUPLICATE_INVOICE_NUMBER');continue
            chosen=[x for x in unique.values() if relevant(x)]
            if not chosen:
                hold(p,'NO_SAME_SOL_CANDIDATE');continue

        good=[];reasons=[]
        for inv in chosen:
            reason=_eligible(inv,p)
            if reason:
                reasons.append(reason);continue
            if remaining[inv['id']]<=0:
                reasons.append('ALREADY_SATISFIED_IN_THIS_SIMULATION');continue
            good.append(inv)
        if p['refs'] and (len(good)!=len(chosen)):
            hold(p,sorted(set(reasons))[0] if reasons else 'INVOICE_INELIGIBLE');continue
        if not good:
            hold(p,sorted(set(reasons))[0] if reasons else 'NO_ELIGIBLE_INVOICE');continue
        if not p['refs']:
            # Never guess a first-match invoice on SOL alone.
            full=[x for x in good if remaining[x['id']]==p['credit']]
            if len(full)!=1:
                reason='AMBIGUOUS_SAME_SOL_CANDIDATES' if len(full)>1 else 'DNM01_OR_PARTIAL_REVIEW_REQUIRED'
                # DNM-01 is an evidence hypothesis, never an auto-allocation.
                rankings=sorted(((abs(remaining[x['id']]-p['credit']),x['id']) for x in good))
                dnm=False
                if len(rankings)>1:
                    first,runner=rankings[0][0],rankings[1][0]
                    dates={x['id']:x['issued'] for x in good}
                    # The approved DNM-01 lead also requires the dominant
                    # candidate to be STRICTLY more recent than runner-up.
                    dnm=(first<=Decimal('1') and runner>=Decimal('2')
                         and runner-first>=Decimal('1')
                         and dates[rankings[0][1]]>dates[rankings[1][1]])
                hold(p,reason,provisional_dnm01=dnm);continue
            chosen=[full[0]]
        else:
            chosen=good
        free=sum((remaining[x['id']] for x in chosen),Decimal('0'))
        if p['credit']>free:
            hold(p,'OVERPAYMENT_OR_DUPLICATE_CREDIT');continue
        # Build all allocations BEFORE updating any temporary balance.
        new=[];unused=p['credit']
        for inv in chosen:
            part=min(unused,remaining[inv['id']]);unused-=part
            if part>0:
                new.append((inv,part))
            if unused==0:break
        if unused!=0 or not new:
            hold(p,'ALLOCATION_ATOMICITY_REVIEW');continue
        for inv,part in new:
            remaining[inv['id']]-=part
            proposals.append(dict(payment_id=p['id'],invoice_no=inv['id'],
                candidate_credit=_s(part),remaining_net=_s(remaining[inv['id']]),
                candidate_status='PROPOSED_FULL' if remaining[inv['id']]==0 else 'PROPOSED_PARTIAL',
                tds_rate_approved_in_fixture=inv['rate'],
                decision='SYNTHETIC_REVIEW_ONLY_NOT_SETTLED'))

    return {
        'engine':'SBI_FRESH_V1_SYNTHETIC_ONLY',
        'rulebook':'Master v2.51 / Matrix v2.39 (reference specification)',
        'activation_cutoff':cutoff.isoformat(),
        'proposals':proposals,'holds':holds,
        'remaining_net':{k:_s(v) for k,v in sorted(remaining.items())},
        'proposal_count':len(proposals),'hold_count':len(holds),
        'source_authentication':'SYNTHETIC_FIXTURE_ONLY',
        'historical_records_accessed':False,
        'financial_writes':False,'production_approved':False,
        'actual_financial_status':'NOT_ASSIGNED',
        'settlements_executed':False,
        'database_connected':False
    }