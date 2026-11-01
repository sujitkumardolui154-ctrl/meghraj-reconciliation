"""Read-only, exact original 53-column to 18-column CREDIT NOTE report.

Input is a separately approved, complete 53-column source CSV, NOT a Firestore
snapshot inferred from duplicate header dictionaries. Does not modify records.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from invoice_source_schema import HEADERS_53

OUTPUT_HEADERS=(
    'FY', 'Invoice Branch', 'Invoice Generate Location', 'Month',
    'Invoice Date', 'Branch Code', 'Client Name', 'GST NO', 'Invoice No',
    'Taxable Amount', 'CGST', 'SGST', 'Total Bill Amount', 'Less TDS',
    'Actual Reciaveable Ammount Deductionof TDS (Including GST)',
    'Taxable Amount Less TDS (Without GST)',
    'Payment Received (If With GST or Excluding GST)', 'Credi note'
)
# Approved source positions: B-H, L-U (zero-based below); note duplicates A/H and G/K.
POSITIONS=(1,2,3,4,5,6,7,11,12,13,14,15,16,17,18,19,20)
MATCH=re.compile(r'\s+')
NUMBER=re.compile(r'-?(?:\d+(?:\.\d*)?|\.\d+)')


def strict_schema(headers):
    actual=tuple(headers)
    expected=tuple(HEADERS_53)
    if len(expected)!=53 or actual!=expected:
        raise ValueError('Input is not the exact approved HEADERS_53 source schema')
    if actual[6]!='Branch Code' or actual[7]!='Client Name' or actual[12]!='Invoice No':
        raise ValueError('Original columns G/H/M changed')
    if actual[20]!='Payment Received ( If With GST or Excluding GST)':
        raise ValueError('Original Column U mismatch')
    return True


def eligible(value):
    return MATCH.sub(' ',str(value or '').strip()).casefold()=='credit note'


def safe_csv(value):
    # Prevent Excel CSV formula execution while leaving original source untouched.
    text=str(value or '')
    candidate=text.lstrip()
    if candidate.startswith(('=','+','@','\t','\r','\n')):
        return "'"+text
    if candidate.startswith('-') and not NUMBER.fullmatch(candidate):
        return "'"+text
    return text


def process_rows(headers, rows, writer):
    strict_schema(headers)
    writer.writerow(OUTPUT_HEADERS)
    seen=set()
    marked=set()
    states=defaultdict(set)
    count=0
    missing=0
    flagged_rows=0
    for line,row in enumerate(rows,2):
        if len(row)!=53:
            raise ValueError(f'Source row {line}: expected 53 columns, got {len(row)}')
        invoice=str(row[12] or '').strip()
        if invoice:
            seen.add(invoice)
        else:
            missing+=1
        is_note=eligible(row[20])
        if invoice:
            states[invoice].add(is_note)
        if is_note:
            flagged_rows+=1
            if invoice:
                marked.add(invoice)
        projected=[safe_csv(row[pos]) for pos in POSITIONS]
        projected.append('CREDIT NOTE' if is_note else '')
        writer.writerow(projected)
        count+=1
    conflicts=sum(1 for statuses in states.values() if len(statuses)>1)
    return {'source_rows':count,'unique_invoice_numbers':len(seen),
            'credit_note_unique_invoices':len(marked),
            'credit_note_rows':flagged_rows,
            'missing_invoice_number_rows':missing,
            'duplicate_conflicting_credit_note_status':conflicts,
            'source_scope':'owner_supplied_53_column_CSV',
            'all_source_invoices_included':True,
            'current_live_firestore_completeness_verified':False,
            'default_firestore_writes':0,'financial_execution':'RESTRICTED'}


def export_csv(source,destination):
    source=Path(source).resolve()
    destination=Path(destination).resolve()
    if not source.is_file() or source.suffix.lower()!='.csv':
        raise ValueError('Approved lossless source CSV file is required')
    if source==destination:
        raise ValueError('Source and output paths must differ')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',newline='',encoding='utf-8-sig',
                                     dir=str(destination.parent),prefix='.sbi_credit_',
                                     suffix='.tmp',delete=False) as out:
        tmp=Path(out.name)
        try:
            with source.open('r',newline='',encoding='utf-8-sig') as original:
                reader=csv.reader(original)
                headers=next(reader)
                summary=process_rows(headers,reader,csv.writer(out,lineterminator='\r\n'))
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    if summary['duplicate_conflicting_credit_note_status'] or summary['missing_invoice_number_rows']:
        tmp.unlink(missing_ok=True)
        raise ValueError('Source contains missing Invoice No or conflicting duplicate statuses; output withheld')
    digest=hashlib.sha256(tmp.read_bytes()).hexdigest()
    os.replace(tmp,destination)
    summary.update({
        'csv_sha256':digest,
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'timestamp_utc':datetime.now(timezone.utc).isoformat(),
        'output_filename':destination.name
    })
    manifest=destination.with_suffix('.manifest.json')
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',
                                     dir=str(destination.parent),prefix='.manifest_',
                                     suffix='.tmp',delete=False) as f:
        interim=Path(f.name)
        json.dump(summary,f,indent=2)
        f.write('\n')
    os.replace(interim,manifest)
    return summary,manifest


def synthetic_qa():
    import io
    from copy import deepcopy
    headers=list(HEADERS_53)
    assert len(headers)==53
    rows=[]
    for invoice,status,branch in [('MXPTEST001','  credit  note ','0016642'),
                                  ('MXPTEST002','PAID','0001234'),
                                  ('MXPTEST001','CREDIT NOTE','0016642')]:
        row=['']*53; row[0]='OTHER CLIENT A';row[7]='CLIENT H'
        row[6]=branch;row[10]='OTHER BRANCH K';row[12]=invoice
        row[13]='100.50';row[20]=status; rows.append(row)
    preserved=deepcopy(rows)
    handle=io.StringIO(newline='')
    summary=process_rows(headers,rows,csv.writer(handle))
    view=list(csv.reader(io.StringIO(handle.getvalue())))
    assert len(view)==4 and all(len(x)==18 for x in view)
    assert view[1][5]=='0016642' and view[1][6]=='CLIENT H'
    assert view[1][8]=='MXPTEST001' and view[1][17]=='CREDIT NOTE'
    assert view[2][17]=='' and view[3][17]=='CREDIT NOTE'
    assert summary['credit_note_unique_invoices']==1
    assert summary['unique_invoice_numbers']==2 and rows==preserved
    assert summary['duplicate_conflicting_credit_note_status']==0
    bad=deepcopy(rows);bad[1][12]='MXPTEST001'
    try:
        h=io.StringIO();summ=process_rows(headers,bad,csv.writer(h))
        assert summ['duplicate_conflicting_credit_note_status']==1
    except Exception as exc:
        raise AssertionError('Conflict flag regression') from exc
    print('APPROVED 18-COLUMN REPORT: PASS')
    print('ALL SOURCE INVOICES INCLUDED: PASS')
    print('ORIGINAL COLUMN U -> OUTPUT COLUMN R: PASS')
    print('TEXT SOL/G AND CLIENT/H POSITIONAL MAPPING: PASS')
    print('DUPLICATE-INVOICE COUNT AND CONFLICT FLAG: PASS')
    print('ORIGINAL SOURCE PRESERVATION: PASS')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',help='Exact approved complete 53-column CSV input')
    p.add_argument('--out',default='reports/credit_note/SBI_CREDIT_NOTE_ALL_INVOICES.csv')
    args=p.parse_args()
    synthetic_qa()
    if args.source:
        # DIL_OPTIONAL_SOURCE_GUARD_V1
        if not args.source:
            print("APPROVED SOURCE: NOT PROVIDED")
            print("SOURCE EXPORT: SKIPPED SAFELY")
            print("REAL CREDIT NOTE COUNT: PENDING")
            return
        result,manifest=export_csv(args.source,args.out)
        print('SOURCE INVOICE ROWS:',result['source_rows'])
        print('UNIQUE CREDIT NOTE INVOICES:',result['credit_note_unique_invoices'])
        print('CREDIT NOTE CSV:',args.out)
        print('SHA256 MANIFEST:',manifest)
        print('CURRENT LIVE FIRESTORE COMPLETENESS: NOT VERIFIED')
    else:
        print('REAL REPORT: AWAITING APPROVED LOSSLESS 53-COLUMN SOURCE CSV')
        print('HINT: SBI_CREDIT_SOURCE=/path/to/current_source.csv bash ~/sbi_credit_note_all_invoices_v1.sh')
    print('FINANCIAL EXECUTION: RESTRICTED')
    print('CREDIT NOTE FULL REPORT MODULE: READY')

if __name__=='__main__':
    main()
