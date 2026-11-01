"""Fail-closed, read-only snapshot loader for the verified 53-column SBI baseline.

Scope: dashboard_report_datasets/<one selected dataset>/rows ONLY.
Completed invoice imports are NOT included; never represent this as a complete ledger.
Never writes to Firestore. Never changes source rows or payment allocations.
"""
from collections.abc import Mapping
from credit_note_csv import build_credit_note_csv
from invoice_source_schema import HEADERS_53

MAX_ROWS = 20000
CANDIDATE_ARRAY_FIELDS = ('values', 'row', 'cells', 'data', 'row_values', 'source_row')


class ContractError(ValueError):
    pass


def extract_positioned_row(raw, selected_field=None):
    if not isinstance(raw, Mapping):
        raise ContractError('Firestore row is not a field mapping')
    candidates = []
    for name in CANDIDATE_ARRAY_FIELDS:
        value = raw.get(name)
        if isinstance(value, (list, tuple)) and len(value) == 53:
            candidates.append((name, value))
    if selected_field is not None:
        candidates = [c for c in candidates if c[0] == selected_field]
    if len(candidates) != 1:
        raise ContractError('Cannot uniquely identify a positional 53-column source row')
    name, values = candidates[0]
    # Never infer a text SOL by converting a numeric source cell.
    sol = values[6]
    if sol is not None and not isinstance(sol, str):
        raise ContractError('Source SOL value is not text: requires review')
    return name, tuple(values)


def load_baseline(db, max_rows=MAX_ROWS):
    """Return one unambiguous dataset baseline and metadata without any write."""
    if max_rows < 1 or max_rows > MAX_ROWS:
        raise ContractError('Unsafe report row limit')
    dataset_collection = db.collection('dashboard_report_datasets')
    datasets = list(dataset_collection.limit(10).stream())
    candidates = []
    for document in datasets:
        if list(document.reference.collection('rows').limit(1).stream()):
            candidates.append(document)
    if len(datasets) == 10 or len(candidates) != 1:
        raise ContractError('Ambiguous baseline dataset selection')
    dataset = candidates[0]
    before = dataset.update_time
    rows = []
    selected_field = None
    for snap in dataset.reference.collection('rows').stream():
        if len(rows) >= max_rows:
            raise ContractError('Baseline exceeds safe row limit')
        field, values = extract_positioned_row(snap.to_dict(), selected_field)
        if selected_field is None:
            selected_field = field
        rows.append(values)
    if not rows:
        raise ContractError('Baseline source empty')
    latest = dataset.reference.get()
    if not latest.exists or latest.update_time != before:
        raise ContractError('Dataset metadata changed during report read')
    # Avoid mixed old-baseline/current-import output. Caller must label baseline scope.
    return rows, {'dataset_document_id':dataset.id, 'source_row_field':selected_field,
                  'baseline_rows':len(rows),'source_scope':'baseline_only',
                  'completed_imports_included':False}


def build_baseline_credit_note(db):
    rows, info = load_baseline(db)
    data, summary = build_credit_note_csv(HEADERS_53, rows)
    return data, {**summary, **info, 'data_connected':True,
                  'full_current_invoice_database':False}
