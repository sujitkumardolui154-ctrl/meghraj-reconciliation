"""Preview-only approved SBI updates. No database, Firestore or Excel writes."""
from decimal import Decimal, InvalidOperation
from invoice_source_schema import HEADERS_53

# Verified SBI position in 53-column source (0-based).
SOL = 6; CLIENT = 7; INVOICE = 12; TAXABLE = 13; MAIL = 30
FIELDS = {'client_name': CLIENT, 'mail_id': MAIL, 'taxable_amount': TAXABLE}


def preview_changes(rows, operation, identifier, proposed):
    """Return an impact preview, never mutate source rows or calculate taxes.

    Branch name requires a separately approved mapping: not implemented here.
    No authoritative financial recalculations occur in this module.
    """
    if len(HEADERS_53) != 53:
        raise ValueError('Unexpected source schema')
    assert HEADERS_53[SOL] == 'Branch Code'
    assert HEADERS_53[CLIENT] == 'Client Name'
    assert HEADERS_53[INVOICE] == 'Invoice No'
    assert HEADERS_53[MAIL] == 'Mail Id'
    if operation not in ('client_name', 'mail_id', 'taxable_amount'):
        raise ValueError('Unsupported operation')
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError('Exact text SOL or invoice required')
    if not isinstance(proposed, str) or not proposed.strip() or len(proposed)>300:
        raise ValueError('Valid proposed text required')
    if operation == 'taxable_amount':
        try:
            val = Decimal(proposed)
            if not val.is_finite() or val < 0 or val.as_tuple().exponent < -2:
                raise ValueError('Invalid taxable amount')
        except InvalidOperation as exc:
            raise ValueError('Invalid taxable amount') from exc
    field = FIELDS[operation]
    key_index = INVOICE if operation == 'taxable_amount' else SOL
    matches = 0; changes = 0; already = 0; samples = []
    seen_invoices = set()
    for row in rows:
        if isinstance(row, (str, bytes, dict)):
            raise ValueError('Exact 53-column positional rows required')
        row = tuple(row)
        if len(row) != 53:
            raise ValueError('Unexpected source row length')
        invoice = str(row[INVOICE] or '').strip()
        if invoice:
            if invoice in seen_invoices:
                raise ValueError('Duplicate invoice identifier: cannot safely preview')
            seen_invoices.add(invoice)
        if str(row[key_index] or '').strip() != identifier:
            continue
        matches += 1
        old = str(row[field] or '')
        if old == proposed:
            already += 1
        else:
            changes += 1
            if len(samples) < 20:
                samples.append({'invoice_no': invoice, 'old': old, 'new': proposed})
    return {'operation': operation, 'exact_identifier': identifier,
            'matched_invoices': matches, 'would_change': changes,
            'already_correct': already, 'preview_samples': samples,
            'committed': False, 'financial_recalculation': 'NOT_PERFORMED'}
