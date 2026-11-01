"""Read-only SBI report export primitives. No Firestore connection or database writes.

Caller must authenticate, authorize and supply already verified report rows.
All records and headers remain untouched; each export is a single-snapshot artifact.
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import datetime, timezone

REPORT_NAMES = {
    'unpaid', 'ok', 'balance-review', 'suspense',
    'reconciliation-changes', 'credit-note', 'log-report'
}
LOG_HEADERS = (
    'Timestamp UTC', 'Username', 'Transaction ID', 'Operation',
    'Source', 'Outcome', 'Old Value SHA256', 'New Value SHA256', 'Stage'
)


def safe_cell(value):
    """Protect spreadsheet readers from formula injection, keep numeric negatives."""
    if value is None:
        return ''
    v = str(value)
    t = v.lstrip(' \t\r\n')
    if t.startswith(('=', '+', '@')):
        return "'" + v
    if t.startswith('-') and not re.fullmatch(r'-\d+(?:\.\d+)?', t):
        return "'" + v
    if v.startswith(('\t','\r','\n')):
        return "'" + v
    return v


def csv_bytes(headers, rows):
    """Preserve exact header text/order, including duplicates found in source."""
    headers = tuple(headers)
    if not headers or len(headers) > 256 or any(not isinstance(h, str) for h in headers):
        raise ValueError('Invalid report headers')
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(headers)
    count = 0
    for row in rows:
        if isinstance(row, Mapping) or isinstance(row, (str, bytes)):
            raise ValueError('Positional row required to preserve duplicate headers')
        values = tuple(row)
        if len(values) != len(headers):
            raise ValueError('Report row/header mismatch')
        writer.writerow([safe_cell(x) for x in values])
        count += 1
    return out.getvalue().encode('utf-8-sig'), count


def build_log_report(events):
    """Produce a report from supplied *existing* audit events; does not create events."""
    rows = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError('Expected audit event dictionary')
        missing = [h for h in LOG_HEADERS if h not in event]
        if missing:
            raise ValueError('Audit fields missing: ' + ', '.join(missing))
        rows.append([event[h] for h in LOG_HEADERS])
    return csv_bytes(LOG_HEADERS, rows)


def build_consolidated_zip(report_sources, snapshot_id, generated_at=None):
    """ZIP selected authorized report snapshots; reject absent or partial datasets.

    report_sources: {report-name: (headers, rows)}, all from same snapshot.
    Does not assert that the approved report suite is complete unless caller
    passes and validates its entire required list.
    """
    if not isinstance(report_sources, Mapping) or not report_sources:
        raise ValueError('At least one report required')
    if not isinstance(snapshot_id, str) or not re.fullmatch(r'[A-Za-z0-9._-]{5,100}', snapshot_id):
        raise ValueError('Valid snapshot identifier required')
    if set(report_sources) - REPORT_NAMES:
        raise ValueError('Unsupported report name')
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    output = io.BytesIO()
    manifest = {'snapshot_id': snapshot_id, 'generated_utc': generated_at,
                'source': 'supplied authorized snapshot', 'reports': []}
    with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(report_sources):
            spec = report_sources[name]
            if not isinstance(spec, (tuple, list)) or len(spec) != 2:
                raise ValueError('Expected headers and rows for ' + name)
            headers, rows = spec
            payload, count = csv_bytes(headers, rows)
            filename = name + '.csv'
            zf.writestr(filename, payload)
            manifest['reports'].append({
                'name': name, 'filename': filename, 'rows': count,
                'sha256': hashlib.sha256(payload).hexdigest()
            })
        zf.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
    return output.getvalue(), manifest
