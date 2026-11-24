"""R27.1: FFI-001 protected fresh-source provenance and XLSX structural preflight.

This is NOT a payment reconciliation runner. It deliberately rejects prior
Drive/Library/Project workbooks as executable sources, and never certifies
that a caller-supplied origin flag is an authenticated current user upload.
That final trust signal requires an independent host attachment receipt.

Source bytes remain in memory: no disk I/O, no worksheet data extraction,
no financial fields, no status changes, no database or network calls.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET
import re

STAGE="R27_1_FFI001_LOCAL_STRUCTURAL_PREFLIGHT_ONLY"
SHEETS=frozenset(("Invoice Details.","PAYMNENT"))
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS="{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL="{http://schemas.openxmlformats.org/package/2006/relationships}"
SHA=re.compile("[0-9a-f]{64}\\Z")
MAX_SOURCE_BYTES=90*1024*1024
MAX_UNCOMPRESSED=400*1024*1024
MAX_MEMBERS=20000

class FreshIntakeRefusal(ValueError):
    """Constant reason code; never disclose bank source text."""


@dataclass(frozen=True)
class FreshIntakeRequest:
    file_name:str
    selected_origin:str
    current_run_id:str
    selected_as_current_run_input:bool
    expected_original_file_sha256:str|None=None


def require(condition,code):
    if not condition:
        raise FreshIntakeRefusal(code)


def _xml(raw):
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(),
            "UNTRUSTED_XML_ENTITIES_REFUSED")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise FreshIntakeRefusal("INVALID_XLSX_XML")


def _safe_target(target):
    require(type(target) is str and target and "\\" not in target
            and not target.lower().startswith(("http:","https:","file:")),
            "UNSAFE_SHEET_RELATIONSHIP")
    pos=target.lstrip("/") if target.startswith("/") else "xl/"+target
    parts=PurePosixPath(pos).parts
    require(all(p not in (".","..") for p in parts)
            and pos.startswith("xl/worksheets/")
            and pos.endswith(".xml"),"UNSAFE_SHEET_RELATIONSHIP")
    return pos


def inspect_fresh_file_structure(source_bytes,request:FreshIntakeRequest, *,
                                  financial_apply="LOCKED"):
    require(financial_apply=="LOCKED","FINANCIAL_APPLY_LOCK_REQUIRED")
    require(type(request) is FreshIntakeRequest,"TRUSTED_HOST_INTAKE_CONTRACT_REQUIRED")
    require(type(request.file_name) is str and request.file_name.lower().endswith(".xlsx"),
            "FRESH_XLSX_FILE_NAME_REQUIRED")
    require(type(request.current_run_id) is str
            and re.fullmatch("[A-Za-z0-9_.:-]{8,100}",request.current_run_id),
            "NEW_CURRENT_RUN_ID_REQUIRED")
    require(request.selected_origin=="CURRENT_RUN_USER_ATTACHMENT"
            and request.selected_as_current_run_input is True,
            "FFI001_FRESH_CURRENT_RUN_USER_UPLOAD_REQUIRED")
    require(type(source_bytes) is bytes and 0<len(source_bytes)<=MAX_SOURCE_BYTES,
            "FRESH_XLSX_SOURCE_BYTES_REQUIRED")
    require(source_bytes[:4]==b"PK\\x03\\x04",
            "INVALID_XLSX_CONTAINER_SIGNATURE")
    digest=sha256(source_bytes).hexdigest()
    if request.expected_original_file_sha256 is not None:
        require(type(request.expected_original_file_sha256) is str
                and SHA.fullmatch(request.expected_original_file_sha256)
                and digest==request.expected_original_file_sha256,
                "FRESH_ORIGINAL_FILE_SHA256_MISMATCH")
    try:
        with ZipFile(BytesIO(source_bytes)) as z:
            info=z.infolist()
            require(len(info)<=MAX_MEMBERS and len(info)>0,
                    "INVALID_XLSX_ENTRY_COUNT")
            names=set()
            total=0
            for entry in info:
                p=entry.filename
                parts=PurePosixPath(p).parts
                require(not p.startswith("/") and "\\" not in p
                        and all(x not in (".","..") for x in parts)
                        and entry.flag_bits & 0x1 == 0,
                        "UNSAFE_ENCRYPTED_OR_TRAVERSAL_XLSX_ENTRY")
                require(p not in names,"DUPLICATE_XLSX_ZIP_MEMBER")
                names.add(p)
                total+=entry.file_size
                require(total<=MAX_UNCOMPRESSED
                        and entry.file_size<=MAX_UNCOMPRESSED,
                        "XLSX_UNCOMPRESSED_SIZE_LIMIT")
                require(entry.file_size<=1000*max(entry.compress_size,1),
                        "XLSX_DECOMPRESSION_RATIO_LIMIT")
            require({"[Content_Types].xml","_rels/.rels",
                     "xl/workbook.xml","xl/_rels/workbook.xml.rels"}<=names,
                    "MISSING_REQUIRED_XLSX_CORE_PARTS")
            require(z.testzip() is None,"CORRUPT_XLSX_ZIP_ENTRY")
            workbook=_xml(z.read("xl/workbook.xml"))
            relationships=_xml(z.read("xl/_rels/workbook.xml.rels"))
            link={}
            for child in relationships.findall(PKG_REL+"Relationship"):
                ident=child.attrib.get("Id")
                if ident and ident in link:
                    raise FreshIntakeRefusal("DUPLICATE_XLSX_RELATIONSHIP")
                if ident:
                    link[ident]=child.attrib
            tabs={}
            for sheet in workbook.findall(".//"+NS+"sheets/"+NS+"sheet"):
                name=sheet.attrib.get("name")
                rel=sheet.attrib.get(REL_NS+"id")
                require(type(name) is str and name not in tabs and rel in link,
                        "INVALID_OR_DUPLICATE_XLSX_SHEET")
                target=link[rel]
                require(target.get("TargetMode") not in ("External","external"),
                        "EXTERNAL_SHEET_RELATIONSHIP_REFUSED")
                path=_safe_target(target.get("Target"))
                require(path in names,"XLSX_SHEET_XML_MISSING")
                tabs[name]={
                    "sheet_xml_exists":True,
                    "is_visible":sheet.attrib.get("state","visible")=="visible",
                }
            require(SHEETS<=tabs.keys(),"REQUIRED_INVOICE_AND_PAYMNENT_TABS_MISSING")
            require(all(tabs[name]["is_visible"] for name in SHEETS),
                    "REQUIRED_FINANCIAL_SHEET_HIDDEN")
    except (BadZipFile,EOFError,OSError):
        raise FreshIntakeRefusal("INVALID_OR_CORRUPT_XLSX_ZIP")
    return {
        "stage":STAGE,
        "file_name":request.file_name,
        "run_id":request.current_run_id,
        "sha256_of_bytes_inspected":digest,
        "original_byte_size":len(source_bytes),
        "required_sheets_present":True,
        "required_sheet_names":tuple(sorted(SHEETS)),
        "financial_header_and_row_count_verified":False,
        "bank_credit_column_i_and_invoice_s_verified":False,
        "source_macros_or_external_links_authorized":False,
        "host_authenticated_fresh_upload_provenance_verified":False,
        "real_original_bank_statement_utr_verified":False,
        "user_selected_role_recorded_but_not_authenticated":True,
        "genuine_financial_source_certified":False,
        "financial_apply_locked":True,
        "final_payment_status":None,
        "real_bank_allocations":0,
        "real_database_writes":0,
        "production_release_authorized":False,
    }
