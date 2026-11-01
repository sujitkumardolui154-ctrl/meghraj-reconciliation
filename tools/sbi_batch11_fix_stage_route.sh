#!/usr/bin/env bash
# SBI Batch 11 — fix known-version private staging route patch, fail closed.
# Does not change Firestore, the financial engine, or main dashboard.
set -Eeuo pipefail
umask 077
cd "$HOME/meghraj-reconciliation"
TARGET="$HOME/sbi_credit_dashboard_batch11.sh"
[ -f "$TARGET" ] || { echo 'STOP: Original Batch 11 script not found'; exit 2; }
python3 - "$TARGET" <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import sys, shutil
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
original='''old=\'\'\'    return jsonify(error='Real Firestore report loader is not connected to this private staging preview',mode='READ_ONLY'),503\'\'\'
lines=source.splitlines(keepends=True)
fn=''.join(lines[f.lineno-1:f.end_lineno])
if fn.count(old)!=1:
    raise SystemExit('STOP: Report placeholder changed; no update made')
newfn=fn.replace(old,\'\'\'    return credit_report_response(request.path)\'\'\')'''
updated='''# SBI_BATCH11_KNOWN_PRIVATE_ROUTE_V2
lines=source.splitlines(keepends=True)
fn=''.join(lines[f.lineno-1:f.end_lineno])
route_names=set()
for dec in f.decorator_list:
    if (isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute)
        and isinstance(dec.func.value,ast.Name) and dec.func.value.id=='app'
        and dec.func.attr in ('get','route') and dec.args
        and isinstance(dec.args[0],ast.Constant)
        and isinstance(dec.args[0].value,str)):
        route_names.add(dec.args[0].value)
if route_names!={'/reports/credit-note.csv','/reports/credit-note/summary'}:
    raise SystemExit('STOP: Existing private report routes changed; unchanged')
known_preview=('Real Firestore report loader is not connected to this private staging preview' in fn
               and "return jsonify(" in fn)
known_batch4=('SBI_BATCH4_PRIVATE_READ_ONLY_BASELINE' in source
              and 'SBI_LIVE_CREDIT_ENABLED' in fn
              and 'build_baseline_credit_note' in fn and 'ContractError' in fn)
if not (known_preview or known_batch4):
    raise SystemExit('STOP: Unrecognized staging report implementation; unchanged')
if not fn.startswith('def real_report():'):
    raise SystemExit('STOP: Report handler signature changed; unchanged')
# Replace only the old private report function body, preserving decorators,
# other routes, feature toggles, HTML, and original source backup.
newfn='def real_report():\\n    return credit_report_response(request.path)\\n' '''
if 'SBI_BATCH11_KNOWN_PRIVATE_ROUTE_V2' in s:
    print('STAGING ROUTE PATCH: ALREADY INSTALLED')
else:
    if s.count(original)!=1:
        raise SystemExit('STOP: Batch 11 patch location changed; no modification')
    candidate=s.replace(original,updated,1)
    backup=p.with_name(p.name+'.before_route_patch_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    shutil.copy2(p,backup)
    p.write_text(candidate,encoding='utf-8')
    print('BATCH 11 ROUTE PATCH: INSTALLED')
    print('ORIGINAL SCRIPT BACKUP:',backup)
PY
bash -n "$TARGET"
echo '===== RESUMING BATCH 11 GUARDED PRIVATE STAGING ====='
bash "$TARGET"
