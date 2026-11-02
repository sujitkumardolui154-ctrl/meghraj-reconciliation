"""Strict, data-preserving Firestore row decoder for SBI's original 53-column source.

Only accepts unambiguous positional records. Unrelated metadata fields are ignored.
No Firestore I/O here and no financial calculations. Never infer from duplicate
human-readable header keys, since G/H and K/A can be different original values.
"""
import re
from datetime import date, datetime
from decimal import Decimal
from collections.abc import Mapping
from hashlib import sha256

N = 53
WRAPPER_KEYS = frozenset(('values','row','cells','data','row_values','source_row','payload','record','fields','source'))

class RowContractError(ValueError):
    pass


def _is_scalar(value):
    return value is None or isinstance(value, (str, int, float, bool, date, datetime, Decimal))


def _ordered_index_map(value):
    if not isinstance(value, Mapping) or len(value) != N:
        return None
    keys = set(value.keys())
    patterns = (
        [str(i) for i in range(N)],
        [f'c{i}' for i in range(N)],
        [f'c_{i}' for i in range(N)],
        [f'col_{i}' for i in range(N)],
        [f'column_{i}' for i in range(N)],
    )
    options = [k for k in patterns if set(k) == keys]
    if len(options) != 1:
        return None
    return [value[k] for k in options[0]]


def _candidate_paths(raw):
    """Return nested, exact positional candidates, without inspecting cell contents for identity."""
    if not isinstance(raw, Mapping):
        raise RowContractError('Row document must be a dictionary')
    found = []
    def search(value, path, depth):
        if isinstance(value, (list, tuple)):
            if len(value) == N and all(_is_scalar(x) for x in value):
                found.append((path, tuple(value)))
            return
        if not isinstance(value, Mapping) or depth >= 4:
            return
        indexed = _ordered_index_map(value)
        if indexed is not None and all(_is_scalar(x) for x in indexed):
            found.append((path + '.indexed' if path else 'indexed', tuple(indexed)))
            return
        for key, item in value.items():
            if key in WRAPPER_KEYS:
                search(item, path + '.' + key if path else key, depth + 1)
    search(raw, '', 0)
    return found


def extract_positioned_row(raw, selected_field=None):
    candidates = _candidate_paths(raw)
    if selected_field is not None:
        candidates = [c for c in candidates if c[0] == selected_field]
    if len(candidates) != 1:
        raise RowContractError('Not exactly one verified 53-column positional row')
    path, values = candidates[0]
    # Preserve SOL text/leading zeros; don't reinterpret numeric values.
    if values[6] is not None and not isinstance(values[6], str):
        raise RowContractError('Branch Code/SOL source is not text')
    if values[12] is not None and not isinstance(values[12], str):
        raise RowContractError('Invoice No source is not text')
    return path, values


def rest_value_to_python(value):
    """Decode documented Firestore REST Value union; unsupported complex cells fail closed."""
    if not isinstance(value, dict):
        raise RowContractError('Malformed Firestore Value')
    if 'nullValue' in value:
        return None
    if 'stringValue' in value:
        return value['stringValue']
    if 'integerValue' in value:
        return int(value['integerValue'])
    if 'doubleValue' in value:
        return float(value['doubleValue'])
    if 'booleanValue' in value:
        return bool(value['booleanValue'])
    if 'timestampValue' in value:
        return value['timestampValue']
    if 'arrayValue' in value:
        return [rest_value_to_python(x) for x in value['arrayValue'].get('values', [])]
    if 'mapValue' in value:
        return {k:rest_value_to_python(v) for k,v in value['mapValue'].get('fields',{}).items()}
    # A timestamp or serialized object is not a supported source cell without explicit policy.
    return _UnsupportedValue()


class _UnsupportedValue:
    """Opaque marker; prevents interpreting unsupported cell types as values."""
    pass


def rest_document_to_python(document):
    return {k:rest_value_to_python(v) for k,v in document.get('fields',{}).items()}


def describe_document_shape(document):
    """Safe structure summary; NEVER stores a cell value, customer name or invoice number."""
    def safe_field_name(key):
        # Keys can be user-derived in arbitrary Firestore maps. Never echo invoice
        # identifiers, emails or customer-related map keys into diagnostic logs.
        if (re.fullmatch(r'[A-Za-z_ ]{1,65}', key) or
                re.fullmatch(r'(?:c|col|column)_?[0-9]{1,2}', key)):
            return key
        return '<masked-field-' + sha256(key.encode()).hexdigest()[:8] + '>'
    def describe(value, depth=0):
        if not isinstance(value, dict):
            return {'kind':'invalid'}
        if 'arrayValue' in value:
            array=value['arrayValue'].get('values',[])
            subtypes=sorted({next(iter(x), 'unknown') for x in array if isinstance(x,dict)})
            return {'kind':'array','length':len(array),'element_types':subtypes}
        if 'mapValue' in value:
            fields=value['mapValue'].get('fields',{})
            if depth>=3:
                return {'kind':'map','field_count':len(fields)}
            return {'kind':'map','fields':{safe_field_name(k):describe(v,depth+1) for k,v in sorted(fields.items())}}
        return {'kind':next(iter(value), 'unknown')}
    return {safe_field_name(k):describe(v) for k,v in sorted(document.get('fields',{}).items())}
