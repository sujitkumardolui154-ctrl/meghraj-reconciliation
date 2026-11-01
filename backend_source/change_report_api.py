"""Authenticated Cloud Run backend receipt report endpoint.
Caller authentication is enforced by the Cloud Run/IAM frontend gateway.
"""
import csv, io, re
from flask import jsonify, Response
from google.cloud import firestore
from change_feature import TAGS

PROJECT='meghraj-reconciliation'
ID=re.compile(r'^[a-f0-9]{32}$')
COLS=('source_row','invoice_no','old_payment','new_payment','tag','previous_report','balance_review','reason')

def handle_change_report(request):
    if request.method != 'GET': return jsonify(error='Method not allowed'),405
    path=request.path.rstrip('/')
    csv_mode=path.endswith('.csv')
    if path not in ('/change-reports','/change-reports.csv'):
        return jsonify(error='Unknown report'),404
    rid=request.args.get('receipt','')
    if not ID.fullmatch(rid): return jsonify(error='Invalid receipt'),400
    db=firestore.Client(project=PROJECT)
    ref=db.collection('dashboard_import_receipts_v140').document(rid)
    snap=ref.get(timeout=15)
    if not snap.exists: return jsonify(error='Not found'),404
    receipt=snap.to_dict() or {}
    if receipt.get('change_audit_state') != 'READY' or receipt.get('status') not in ('PREVIEW_READY','APPLYING','COMPLETED'):
        return jsonify(error='Change audit unavailable'),409
    expected=receipt.get('change_audit_total')
    if type(expected) is not int or expected<0 or expected>20000:
        return jsonify(error='Invalid audit manifest'),503
    rows=[]; cursor=None; query=ref.collection('change_audit').order_by('__name__')
    while len(rows)<expected:
        q=query.limit(min(250, expected-len(rows)))
        if cursor is not None:q=q.start_after(cursor)
        docs=q.get(timeout=30)
        if not docs:break
        rows.extend(d.to_dict() for d in docs)
        cursor=docs[-1]
    if len(rows)!=expected or any(r.get('tag') not in TAGS for r in rows):
        return jsonify(error='Audit incomplete'),503
    if not csv_mode:
        response=jsonify(version='1.0.0',receipt=rid,total=expected,
            summary=receipt.get('change_audit_summary'),
            report_breakdown=receipt.get('change_audit_breakdown'),
            details=rows[:100],details_truncated=len(rows)>100,
            csv_url='/api/reports/reconciliation-changes.csv?receipt='+rid)
    else:
        s=io.StringIO(newline='');writer=csv.writer(s);writer.writerow(COLS)
        for r in rows:
            cells=[]
            for col in COLS:
                value=str(r.get(col,'') if r.get(col) is not None else '')
                if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')):value="'"+value
                cells.append(value)
            writer.writerow(cells)
        response=Response(s.getvalue().encode('utf-8-sig'),content_type='text/csv; charset=utf-8')
        response.headers['Content-Disposition']='attachment; filename="reconciliation-changes-'+rid+'.csv"'
        response.headers['X-Report-Rows']=str(expected)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response
