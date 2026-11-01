"""Immutable receipt-linked invoice comparison. Never modifies financial rows."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from invoice_source_schema import invoice_number, row_layout
from payment_report_rules import payment_report_kind

TAGS = ('NEW','UNCHANGED','PAYMENT_ADDED','PAYMENT_CHANGED','PAYMENT_CLEARED_REVIEW','CONFLICT')
CATEGORIES = ('unpaid','ok','error-value','balance-review')

def payment(row):
    w, _, i, _, _ = row_layout(row)
    types = row.get('original_cell_types')
    if not isinstance(types, list) or len(types) != w:
        return None, 'INVALID_CELL_TYPES'
    t = types[i]
    raw = row['original_values'][i]
    if t in ('e','b','f','d') or t not in ('n','s','str','inlineStr'):
        return None, 'INVALID_PAYMENT_CELL_TYPE'
    if not raw.strip():
        return None, None
    # Strict canonical numeric form; match existing report rules for numeric classifications.
    if payment_report_kind(row) == 'error-value':
        return None, 'INVALID_PAYMENT_VALUE'
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return None, 'INVALID_PAYMENT_VALUE'
    if not value.is_finite():
        return None, 'INVALID_PAYMENT_VALUE'
    return value, None

def change_report(existing, incoming, rejected=()):
    """Inputs are validated parsed rows; rejected rows get individual CONFLICT records."""
    existing, incoming, rejected = list(existing), list(incoming), list(rejected)
    old = {}
    old_dupes = set()
    for r in existing:
        number = invoice_number(r)
        if not number:
            continue
        if number in old: old_dupes.add(number)
        else: old[number] = r
    counts = Counter(invoice_number(r) for r in incoming)
    counts.update(str(r.get('invoice_no') or '') for r in rejected)
    details = []
    for r in incoming:
        number = invoice_number(r)
        previous = old.get(number)
        issue = ''
        before, after = None, None
        if not number: issue = 'MISSING_INVOICE_NO'
        elif number in old_dupes: issue = 'DUPLICATE_EXISTING'
        elif counts[number] > 1: issue = 'DUPLICATE_UPLOAD'
        try:
            after, error = payment(r)
            if error: issue = error
            if previous:
                before, old_error = payment(previous)
                if old_error: issue = 'INVALID_EXISTING_PAYMENT'
        except (KeyError, ValueError, IndexError, TypeError):
            issue = 'INVALID_SOURCE_ROW'
        if issue: tag = 'CONFLICT'
        elif previous is None: tag = 'NEW'
        elif before == after: tag = 'UNCHANGED'
        elif before is None: tag = 'PAYMENT_ADDED'
        elif after is None: tag = 'PAYMENT_CLEARED_REVIEW'
        else: tag = 'PAYMENT_CHANGED'
        category = None
        balance_review = False
        if previous:
            try:
                category = previous.get('payment_report') or payment_report_kind(previous)
                balance_review = previous.get('balance_valid') is False
            except (ValueError, KeyError, TypeError):
                issue = 'INVALID_PREVIOUS_CATEGORY'; tag = 'CONFLICT'
        details.append(dict(invoice_no=number, source_row=r.get('source_row'),tag=tag,
                            old_payment='' if before is None else str(before),
                            new_payment='' if after is None else str(after),
                            previous_report=category,balance_review=balance_review,reason=issue))
    for r in rejected:
        details.append(dict(invoice_no=str(r.get('invoice_no') or ''),source_row=r.get('source_row'),
            tag='CONFLICT',old_payment='',new_payment='',previous_report=None,
            balance_review=False,reason=','.join(map(str,r.get('reasons') or ['PARSER_REJECTED']))))
    summary = {t: 0 for t in TAGS}
    breakdown = {c:{t:0 for t in TAGS} for c in (*CATEGORIES,'unclassified')}
    for d in details:
        t=d['tag']; summary[t]+=1
        c=d['previous_report'] if d['previous_report'] in CATEGORIES[:3] else 'unclassified'
        breakdown[c][t]+=1
        if d['balance_review']: breakdown['balance-review'][t]+=1
    total=len(incoming)+len(rejected)
    if sum(summary.values()) != total or len(details) != total:
        raise ValueError('Invoice change count mismatch')
    return {'version':'1.0.0','total':total,'summary':summary,'report_breakdown':breakdown,
            'details':details,'database_changed':False,'reconciliation_executed':False}
