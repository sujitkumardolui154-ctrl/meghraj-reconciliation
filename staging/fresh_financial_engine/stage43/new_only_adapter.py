"""NEW engine 21 11 2026 — Stage 4.3 verified-layout SYNTHETIC source bridge.

Reads only fabricated SYNTHETIC_* two-sheet NEW_ONLY workbooks.  The source
headers/coordinates were recovered from header-only profile evidence; NEVER
promotes new-format invoices to the overlapping legacy v2.18 output writer.

HMAC attestation proves an *internal gateway signer*, not the original SBI
bank or invoice authority. No real input, historical rows, finance writer,
settlement, or production Apply is accepted by this module.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import posixpath
import re
import tempfile
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from sbi_engine.reference_schema import (
    INVOICE_COLUMNS, INVOICE_HEADERS, INVOICE_SHEET,
    PAYMENT_COLUMNS, PAYMENT_HEADERS, PAYMENT_SHEET, validate_reference_headers,
)
from stage4_ledger import (
    NewOnlyCandidateLedger, Principal, Stage4Policy, bank_fields,
    invoice_fields, paise, upload_row_sha256, verify_attestation,
)

SHEETS = (PAYMENT_SHEET, INVOICE_SHEET)
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
COL_ADDR = re.compile(r'([A-Z]{1,3})([1-9][0-9]{0,5})\Z')
MAX_SIZE = 2_000_000
MAX_MEMBER = 3_000_000
MAX_MEMBERS = 90
MAX_ROWS = 100


class NewSourceBlocked(ValueError):
    """Unapproved/malformed new source or conflicting signed evidence."""


def require(cond: bool, reason: str) -> None:
    if not cond:
        raise NewSourceBlocked(reason)


def column_index(alpha: str) -> int:
    value = 0
    for ch in alpha:
        value = value * 26 + ord(ch) - 64
    return value


def _xl_snapshot(source: Path) -> tuple[tuple[str, ...], dict[str, dict[tuple[int, int], tuple[str, str | None, str | None]]]]:
    """Read-only OOXML snapshot. File content is never edited or saved."""
    require(source.name.startswith('SYNTHETIC_') and source.suffix.lower()=='.xlsx',
            'SYNTHETIC_TWO_SHEET_FILE_ONLY')
    require(source.is_file() and not source.is_symlink() and 0 < source.stat().st_size <= MAX_SIZE,
            'SYNTHETIC_SOURCE_SIZE_OR_TYPE_INVALID')
    try:
        with ZipFile(source) as z:
            names = z.namelist()
            require(len(names) <= MAX_MEMBERS and len(set(names)) == len(names),
                    'XLSX_ARCHIVE_MEMBERS_INVALID')
            require(not any(n.startswith('/') or '..' in n.split('/') or n.endswith('.bin')
                            or n.startswith('xl/externalLinks/') for n in names),
                    'XLSX_UNSAFE_ARCHIVE_MEMBER')
            require(not any(info.file_size > MAX_MEMBER for info in z.infolist()),
                    'XLSX_EXPANDED_MEMBER_TOO_LARGE')
            for needed in ('xl/workbook.xml', 'xl/_rels/workbook.xml.rels'):
                require(needed in names, 'XLSX_PACKAGE_STRUCTURE_INVALID')
            shared: list[str] = []
            if 'xl/sharedStrings.xml' in names:
                sroot = ET.fromstring(z.read('xl/sharedStrings.xml'))
                shared = [''.join(t.text or '' for t in si.findall('.//s:t', NS))
                          for si in sroot.findall('s:si', NS)]
            workbook = ET.fromstring(z.read('xl/workbook.xml'))
            relroot = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
            relationships = {e.attrib['Id']: e.attrib['Target']
                             for e in relroot.findall('p:Relationship', NS)}
            sheets: dict[str, dict[tuple[int,int],tuple[str,str|None,str|None]]] = {}
            tabs: list[str] = []
            for n in workbook.findall('s:sheets/s:sheet', NS):
                name = n.attrib.get('name', '')
                require(name and name not in sheets, 'XLSX_DUPLICATE_SHEET_NAME')
                ref = n.attrib.get('{%s}id' % NS['r'], '')
                require(ref in relationships, 'XLSX_MISSING_SHEET_RELATIONSHIP')
                target = relationships[ref]
                member = (target.lstrip('/') if target.startswith('/') else
                          posixpath.normpath('xl/' + target))
                require(member.startswith('xl/worksheets/') and member in names,
                        'XLSX_INVALID_SHEET_PATH')
                root = ET.fromstring(z.read(member))
                cells: dict[tuple[int,int],tuple[str,str|None,str|None]] = {}
                for c in root.findall('.//s:sheetData/s:row/s:c', NS):
                    m = COL_ADDR.fullmatch(c.attrib.get('r',''))
                    require(m is not None, 'XLSX_INVALID_CELL_ADDRESS')
                    col,row = column_index(m[1]),int(m[2])
                    require(1 <= row <= MAX_ROWS + 1 and 1 <= col <= 50,
                            'XLSX_NEW_SOURCE_LIMIT_EXCEEDED')
                    require((row,col) not in cells, 'XLSX_DUPLICATE_CELL')
                    typ = c.attrib.get('t','n')
                    val = c.find('s:v', NS); form = c.find('s:f', NS)
                    inline = c.find('s:is', NS)
                    text = val.text if val is not None else None
                    if typ=='s':
                        require(text is not None and text.isdecimal() and int(text)<len(shared),
                                'XLSX_BAD_SHARED_STRING_REFERENCE')
                        text=shared[int(text)]; kind='text'
                    elif typ=='inlineStr':
                        text=''.join(t.text or '' for t in inline.findall('.//s:t', NS)) if inline is not None else ''
                        kind='text'
                    elif typ == 'str':
                        kind='text'
                    elif typ == 'b':
                        kind='bool'
                    elif typ == 'e':
                        kind='error'
                    elif typ in ('n',''):
                        kind='number'
                    else:
                        raise NewSourceBlocked('XLSX_UNSUPPORTED_CELL_TYPE')
                    formula = form.text if form is not None else None
                    if text is not None or formula is not None:
                        cells[(row,col)] = (kind,text,formula)
                sheets[name] = cells
                tabs.append(name)
    except (BadZipFile, KeyError, ET.ParseError, OSError, ValueError, OverflowError) as exc:
        if isinstance(exc, NewSourceBlocked):
            raise
        raise NewSourceBlocked('XLSX_READONLY_PARSE_FAILED') from exc
    return tuple(tabs),sheets


def _cell(cells: dict, row: int, col: int, *, optional:bool=False) -> tuple:
    value=cells.get((row,col))
    if optional and value is None:
        return ('blank',None,None)
    require(value is not None and value[2] is None and value[0] not in ('error','bool'),
            f'SOURCE_CELL_MISSING_OR_FORMULA_{row}_{col}')
    return value


def text_cell(cells:dict,row:int,col:int)->str:
    k,v,_=_cell(cells,row,col)
    require(k=='text' and v is not None, f'SOURCE_TEXT_CELL_REQUIRED_{row}_{col}')
    return v


def amount_cell(cells:dict,row:int,col:int)->int:
    k,v,_=_cell(cells,row,col)
    require(k in ('number','text') and v is not None,
            f'SOURCE_AMOUNT_CELL_REQUIRED_{row}_{col}')
    try:
        d=Decimal(str(v))
        cents=d*100
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise NewSourceBlocked(f'SOURCE_AMOUNT_NOT_DECIMAL_{row}_{col}') from exc
    require(d.is_finite() and d >= 0 and cents == cents.to_integral_value(),
            f'SOURCE_AMOUNT_NOT_EXACT_PAISE_{row}_{col}')
    return int(cents)


def snapshot_contract(tabs:tuple[str,...],sheets:dict,bank:dict,invoice:dict,
                      upload_row:dict,policy:Stage4Policy) -> dict:
    """Pure new-format coordinate mapping; caller must separately verify HMACs.

    Only the two standard original tabs.  New invoice A:AI is source data;
    the legacy v2.18 model AI:AM overlaps and MUST NOT be used.
    """
    require(tabs == SHEETS and set(sheets)==set(SHEETS), 'EXACT_TWO_SOURCE_SHEETS_REQUIRED')
    for sheet_name,expected in ((PAYMENT_SHEET,PAYMENT_HEADERS),(INVOICE_SHEET,INVOICE_HEADERS)):
        cells=sheets[sheet_name]
        row1 = [text_cell(cells,1,c) for c in range(1,len(expected)+1)]
        try:
            validate_reference_headers(sheet_name,row1)
        except ValueError as exc:
            raise NewSourceBlocked(str(exc)) from exc
    pay=sheets[PAYMENT_SHEET];inv=sheets[INVOICE_SHEET]
    require(not any(col > 12 for row,col in pay),
            'PAYMENT_SOURCE_EXTRA_COLUMN_FORBIDDEN')
    require(not any(col > 35 for row,col in inv),
            'INVOICE_SOURCE_EXTRA_COLUMN_FORBIDDEN')
    p=bank['source_row'];i=invoice['source_row']
    require(type(p) is int and type(i) is int and 2 <= p <= MAX_ROWS+1 and 2 <= i <= MAX_ROWS+1,
            'NEW_SOURCE_ROW_OUT_OF_BOUND')
    require({row for row,col in pay if row>1 and col<=12}=={p} and
            {row for row,col in inv if row>1 and col<=35}=={i},
            'SINGLE_NEW_ONLY_SYNTHETIC_PAIR_REQUIRED')
    require(text_cell(pay,p,5)==bank['description'], 'BANK_DESCRIPTION_SOURCE_CONFLICT')
    require(text_cell(pay,p,6)==bank['sol_id'], 'BANK_SOL_TEXT_SOURCE_CONFLICT')
    require(text_cell(pay,p,3)==bank['bank_date'], 'BANK_DATE_SOURCE_CONFLICT')
    require(amount_cell(pay,p,9)==paise(bank['credit_amount']), 'BANK_CREDIT_I_SOURCE_CONFLICT')
    require(upload_row_sha256(upload_row)==bank['upload_row_sha256'] and
            upload_row['Description']==bank['description'] and
            upload_row['SOL ID']==bank['sol_id'] and
            paise(upload_row['Credit Amount'])==paise(bank['credit_amount']),
            'UPLOAD_ROW_SOURCE_CONFLICT')
    positions = {'service_month':5, 'invoice_date':6,'sol_id':7,
                 'client_name':8,'invoice_no':11}
    for field,column in positions.items():
        require(text_cell(inv,i,column)==invoice[field],
                f'INVOICE_{field.upper()}_SOURCE_CONFLICT')
    for field,column in (('taxable',12),('cgst',13),('sgst',14),('gross',15)):
        require(amount_cell(inv,i,column)==paise(invoice[field],nonzero=field in ('taxable','gross')),
                f'INVOICE_{field.upper()}_AMOUNT_CONFLICT')
    paid = _cell(inv,i,19,optional=True)
    require(paid[1] in (None,'') and paid[2] is None,
            'PAID_MARKER_NONBLANK_INCLUDING_ZERO')
    require(bank['invoice_reference']==invoice['invoice_no'] and
            bank['sol_id']==invoice['sol_id'] and
            bank['client_name']==invoice['client_name'] and
            bank['service_month']==invoice['service_month'],
            'SIGNED_CROSS_SOURCE_IDENTITY_CONFLICT')
    require(0 <= (date.fromisoformat(bank['bank_date'])-
                  date.fromisoformat(invoice['invoice_date'])).days <= 180,
            'DATE_CHRONOLOGY_OR_180D_CONFLICT')
    # No output writer, real financial allocations or bank proof.
    return {'source_layout':'NEW_35_COLUMN_INVOICE_12_COLUMN_PAYMENT',
            'invoice_no_source_column':'K','gross_source_column':'O',
            'original_paid_marker_column':'S',
            'output_writer_legacy_v218_compatible':False,
            'reason':'ORIGINAL_INVOICE_AI_CONFLICTS_WITH_V218_AI_MODEL',
            'payment_row':p,'invoice_row':i,
            'original_source_cells_preserved':True,
            'bank_origin_independently_authenticated':False,
            'official_master_approved':False,
            'financial_writes':False}


def review_new_only_pair(*,source_xlsx:str|Path,payment_row:dict,bank_evidence:dict,
                         bank_tag:str,invoice_evidence:dict,invoice_tag:str,
                         policy:Stage4Policy,uploader:Principal,reviewer:Principal) -> dict[str,Any]:
    """Signed evidence -> exact new layout -> separate review, no reservation.

    A temporary SQLite file is opened under TemporaryDirectory and destroyed
    afterward. No caller-controlled finance DB path or posting credentials.
    """
    require(type(policy) is Stage4Policy and policy.finance_apply_enabled is False,
            'FINANCIAL_APPLY_LOCK_REQUIRED')
    require(type(uploader) is Principal and uploader.role=='INTAKE' and
            type(reviewer) is Principal and reviewer.role=='REVIEWER' and
            uploader.uid!=reviewer.uid,'DISTINCT_TRUSTED_HOST_ROLES_REQUIRED')
    bank,_ = verify_attestation(bank_evidence,bank_tag,policy,'bank')
    invoice,_ = verify_attestation(invoice_evidence,invoice_tag,policy,'invoice')
    bank_fields(bank,policy)
    invoice_fields(invoice,policy)
    source=Path(source_xlsx)
    tabs,sheets=_xl_snapshot(source)
    digest=sha256(source.read_bytes()).hexdigest()
    require(bank['source_sha256']==digest and invoice['source_sha256']==digest,
            'SIGNED_WORKBOOK_SHA256_CONFLICT')
    result=snapshot_contract(tabs,sheets,bank,invoice,payment_row,policy)
    with tempfile.TemporaryDirectory(prefix='SBI_NEW_ONLY_SYNTHETIC_') as tmp:
        with NewOnlyCandidateLedger(str(Path(tmp)/'candidate.sqlite3'),policy) as ledger:
            ledger.stage_uploaded_bank(payment_row,bank,bank_tag,actor=uploader)
            ledger.record_invoice(invoice,invoice_tag,actor=uploader)
            ledger.review_bank(bank['payment_reference'],actor=reviewer)
            stat=ledger.status()
            require(stat['counts']['receipts']==1 and stat['counts']['invoices']==1 and
                    stat['counts']['reservations']==0,'LEDGER_REVIEW_ONLY_EXPECTED')
    return {**result,'status':'SYNTHETIC_NEW_ONLY_SOURCE_REVIEWED_NOT_RECONCILED',
            'receipt_reviewed':True,'candidate_reservations':0,
            'source_kind':'SYNTHETIC_FIXTURE_ONLY','production_apply_enabled':False,
            'finance_ledger_connected':False,'ledger_persisted_after_review':False,
            'independent_bank_source_authentication':'NOT_IMPLEMENTED',
            'legacy_v218_export':'BLOCKED_SOURCE_COLUMN_OVERLAP'}
