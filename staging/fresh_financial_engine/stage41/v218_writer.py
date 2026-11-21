"""NEW engine 21 11 2026: OUT-SCHEMA-V218-001 *synthetic review* writer.

Standalone OUTPUT only. Never reads a banking source, never calculates matches,
never assigns financial OK, and cannot post to a ledger. The reviewed manifest
is derived from the original Oct 28 v2.18 header-lock archive. Original source
cells are snapshotted using OOXML in READ-ONLY mode before and after the
artifact_tool workbook export, and an unsafe export fails before publication.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import posixpath
import re
import tempfile
from typing import Any
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from artifact_tool import Blob, SpreadsheetFile

BASE=Path(__file__).resolve().parent
MANIFEST=BASE/'references'/'V218_OUTPUT_HEADER_LOCK_MANIFEST.json'
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p':'http://schemas.openxmlformats.org/package/2006/relationships'}
COLUMN_RE=re.compile(r'([A-Z]{1,3})([1-9][0-9]{0,6})\Z')
MODEL_PAYMENT_COLS=tuple(range(13,24))
MODEL_INVOICE_COLS=tuple(range(35,40))
MAX_BYTES=2_500_000

class OutputReviewBlocked(ValueError):
    """Fail closed rather than deliver an altered source workbook."""

def _deny(code: str):
    raise OutputReviewBlocked(code)

def _col_idx(letters: str) -> int:
    n=0
    for c in letters:n=n*26+ord(c)-64
    return n

def _read_snap(path: Path) -> tuple[list[str],dict[str,dict[tuple[int,int],tuple[str,str|None,str|None]]]]:
    """READ-ONLY OOXML semantic cell audit: raw type/value/formula, no modification.

    Shared/inline strings are resolved so OOXML storage representation changes
    cannot mask a changed underlying Excel string. Exact Excel number lexemes
    are preserved: a source's '00012' must never become number 12.
    """
    if not path.is_file() or path.stat().st_size>MAX_BYTES:
        _deny('SYNTHETIC_SOURCE_MISSING_OR_TOO_LARGE')
    with ZipFile(path) as z:
        if len(z.namelist())>1500: _deny('UNEXPECTED_WORKBOOK_COMPLEXITY')
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared=[''.join((t.text or '') for t in si.findall('.//m:t',NS))
                    for si in root.findall('m:si',NS)]
        book=ET.fromstring(z.read('xl/workbook.xml'))
        relroot=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rels={node.attrib['Id']:node.attrib['Target'] for node in relroot.findall('p:Relationship',NS)}
        tabs=[]; sheets={}
        for node in book.findall('m:sheets/m:sheet',NS):
            name=node.attrib['name']
            if name in sheets:_deny('DUPLICATE_SHEET_NAME')
            ref=node.attrib.get('{%s}id'%NS['r'])
            if ref not in rels:_deny('INVALID_WORKBOOK_RELATIONSHIP')
            target=rels[ref]
            member=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            if member not in z.namelist():_deny('MISSING_SHEET_XML')
            root=ET.fromstring(z.read(member))
            cells={}
            for cell in root.findall('.//m:sheetData/m:row/m:c',NS):
                address=cell.attrib.get('r','')
                m=COLUMN_RE.fullmatch(address)
                if m is None:_deny('INVALID_CELL_ADDRESS')
                col,row=_col_idx(m[1]),int(m[2])
                typ=cell.attrib.get('t','n')
                val=cell.find('m:v',NS); f=cell.find('m:f',NS)
                inline=cell.find('m:is',NS)
                raw=val.text if val is not None else None
                if typ=='s':
                    try:raw=shared[int(raw)]
                    except (IndexError,TypeError,ValueError):_deny('INVALID_SHARED_STRING')
                    kind='text'
                elif typ=='inlineStr':
                    raw=''.join((t.text or '') for t in inline.findall('.//m:t',NS)) if inline is not None else ''
                    kind='text'
                elif typ in ('str','e'):
                    kind='text' if typ=='str' else 'error'
                elif typ=='b':
                    kind='bool'
                else:
                    kind='number'
                formula=f.text if f is not None else None
                if raw is not None or formula is not None:
                    cells[(row,col)]=(kind,raw,formula)
            sheets[name]=cells
            tabs.append(name)
    return tabs,sheets

def _protected(snapshot:tuple)->dict:
    _,sheets=snapshot
    return {name:{k:v for k,v in cells.items() if k[1]<=end}
            for name,cells in sheets.items()
            for end in ([12] if name=='PAYMNENT' else [34] if name=='Invoice Details.' else [10000])}

def _cell_text(cells:dict, row:int,col:int)->str:
    v=cells.get((row,col));return '' if v is None or v[1] is None else str(v[1])

def _headers(manifest:dict,tab:str,start:int,stop:int)->list[str]:
    return [manifest['headers'][tab][str(i)] for i in range(start,stop+1)]

def _check_input(source:tuple,manifest:dict):
    tabs,sheets=source
    if tabs!=manifest['sheets']:_deny('SOURCE_SHEET_ORDER_MISMATCH')
    for tab,n in (('PAYMNENT',12),('Invoice Details.',34)):
        for col in range(1,n+1):
            if _cell_text(sheets[tab],1,col)!=manifest['headers'][tab][str(col)]:
                _deny('PROTECTED_HEADER_MISMATCH')
        extra=MODEL_PAYMENT_COLS if tab=='PAYMNENT' else MODEL_INVOICE_COLS
        for (row,col),value in sheets[tab].items():
            if col in extra and (value[1] is not None or value[2] is not None):
                _deny('EXISTING_MODEL_DATA_FORBIDDEN')

def _candidate_rows(cells:dict,protected_end:int)->set[int]:
    return {row for row,col in cells if row>1 and col<=protected_end}

def _validate_values(rows:dict,count:int,which:str):
    if type(rows) is not dict:_deny('MODEL_ROWS_MAPPING_REQUIRED')
    for row,values in rows.items():
        if type(row) is not int or row<2 or type(values) is not list or len(values)!=count:
            _deny('MODEL_ROW_SHAPE_INVALID:'+which)
        for v in values:
            if v is not None and type(v) not in (str,int,float,bool):
                _deny('MODEL_SCALAR_TYPE_INVALID')
            if type(v) is str and (v.startswith(('=','+','-','@','\t','\r','\n')) or len(v)>500):
                _deny('MODEL_FORMULA_OR_LONG_TEXT_DENIED')
    return rows

def write_synthetic_v218_review(source: str|Path,destination: str|Path,
                                payment_models:dict[int,list[Any]],
                                invoice_models:dict[int,list[Any]]|None=None,
                                *,manifest_path:str|Path|None=None)->dict:
    """Write only synthetic *SUSPENSE review* results; never creates financial OK.

    The input must be a SYNTHETIC_* workbook, all payment rows supplied,
    every model cell unoccupied, and original columns exactly preserved.
    This tool has no API capable of reading or updating historical records.
    """
    src,dst=Path(source),Path(destination)
    if (not src.name.startswith('SYNTHETIC_') or
        not dst.name.startswith('SYNTHETIC_') or src.suffix!='.xlsx' or dst.suffix!='.xlsx'):
        _deny('SYNTHETIC_FILENAME_REQUIRED')
    if src.resolve()==dst.resolve():_deny('SOURCE_OVERWRITE_FORBIDDEN')
    if dst.exists():_deny('OUTPUT_OVERWRITE_FORBIDDEN')
    manifest=json.loads(Path(manifest_path or MANIFEST).read_text('utf-8'))
    if manifest['rule_id']!='OUT-SCHEMA-V218-001':_deny('OUTPUT_CONTRACT_INVALID')
    before=_read_snap(src)
    _check_input(before,manifest)
    rows=_candidate_rows(before[1]['PAYMNENT'],12)
    if set(payment_models)!=rows:_deny('MISSING_OR_EXTRA_PAYMENT_ROWS')
    invoices=_candidate_rows(before[1]['Invoice Details.'],34)
    if invoice_models is None:invoice_models={}
    if not set(invoice_models).issubset(invoices):_deny('UNKNOWN_INVOICE_MODEL_ROW')
    _validate_values(payment_models,11,'PAYMNENT')
    _validate_values(invoice_models,5,'INVOICE')
    for values in payment_models.values():
        if values[0]!='SUSPENSE':_deny('REVIEW_ONLY_STATUS_MUST_BE_SUSPENSE')
        if type(values[1]) is not str or not values[1].strip():_deny('REVIEW_REMARK_REQUIRED')
        if values[9] is not None and type(values[9]) is not str:_deny('TEXT_SOL_ID_REQUIRED')
    for values in invoice_models.values():
        if values[0] is not None and type(values[0]) is not str:_deny('TEXT_SOL_ID_REQUIRED')
    # Avoid assigning any new linked-bank model evidence to an already paid row.
    for row,values in invoice_models.items():
        if (row,19) in before[1]['Invoice Details.'] and any(v is not None and v!='' for v in values[2:]):
            _deny('PAID_MARKER_INVOICE_LINK_FORBIDDEN')

    wb=SpreadsheetFile.import_xlsx(Blob.load(str(src)))
    pay=wb.worksheets.get_item('PAYMNENT')
    inv=wb.worksheets.get_item('Invoice Details.')
    pay.get_range('M1:W1').values=[_headers(manifest,'PAYMNENT',13,23)]
    inv.get_range('AI1:AM1').values=[_headers(manifest,'Invoice Details.',35,39)]
    for row,values in sorted(payment_models.items()):pay.get_range(f'M{row}:W{row}').values=[values]
    for row,values in sorted(invoice_models.items()):inv.get_range(f'AI{row}:AM{row}').values=[values]
    # Force model SOL IDs to text, including numeric-looking strings '00001'.
    pay.get_range(f'V2:V{max(rows)}').set_number_format('@') if rows else None
    if invoice_models:
        inv.get_range(f'AI2:AI{max(invoice_models)}').set_number_format('@')
    dst.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='SYNTHETIC_V218_TMP_',suffix='.xlsx',dir=dst.parent)
    os.close(fd)
    tmp=Path(tmp)
    try:
        SpreadsheetFile.export_xlsx(wb).save(str(tmp))
        after=_read_snap(tmp)
        if before[0]!=after[0]:_deny('OUTPUT_SHEET_ORDER_CHANGED')
        if _protected(before)!=_protected(after):_deny('PROTECTED_SOURCE_TYPE_VALUE_OR_FORMULA_CHANGED')
        if after[1]['PAYMNENT'].get((1,13)) is None:_deny('MODEL_HEADERS_MISSING')
        for tab,start,stop in (('PAYMNENT',13,23),('Invoice Details.',35,39)):
            for col in range(start,stop+1):
                if _cell_text(after[1][tab],1,col)!=manifest['headers'][tab][str(col)]:
                    _deny('MODEL_HEADER_MISMATCH')
        for row in rows:
            if _cell_text(after[1]['PAYMNENT'],row,13)!='SUSPENSE':
                _deny('PAYMENT_STATUS_NOT_CONSERVATIVE')
        # Preserve source numeric-looking IDs as TEXT in all protected columns.
        # For added model SOL, validate type+value rather than display formatting.
        for row,values in payment_models.items():
            if values[9] is not None:
                actual=after[1]['PAYMNENT'].get((row,22))
                if actual is None or actual[0]!='text' or actual[1]!=values[9]:
                    _deny('PAYMENT_MODEL_TEXT_SOL_CORRUPTED')
        for row,values in invoice_models.items():
            if values[0] is not None:
                actual=after[1]['Invoice Details.'].get((row,35))
                if actual is None or actual[0]!='text' or actual[1]!=values[0]:
                    _deny('INVOICE_MODEL_TEXT_SOL_CORRUPTED')
        # Exclusive publication: destination cannot be overwritten by a race.
        try:os.link(tmp,dst)
        except FileExistsError:_deny('OUTPUT_ALREADY_EXISTS_CONCURRENTLY')
        return {'status':'SYNTHETIC_SUSPENSE_REVIEW_ONLY',
                'output_schema':'OUT-SCHEMA-V218-001',
                'payment_rows':len(rows),'invoice_model_rows':len(invoice_models),
                'source_cells_preserved':True,'source_types_preserved':True,
                'no_financial_allocations':True,'financial_writes':False,
                'production_approved':False,'historical_records_processed':False}
    finally:
        tmp.unlink(missing_ok=True)