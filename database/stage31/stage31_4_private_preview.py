"""Stage 31.4 private Flask upload PREVIEW candidate. NO PostgreSQL writer.

Not registered in the live PR129 app, and 404 by default even if registered.
Callers MUST inject real server-side Firebase-session and CSRF verifiers; client
headers/user IDs are never accepted as proof of authentication. No apply route
can commit data. Only source-contract previews are returned, no invoice values.
"""
import hashlib
import io
import logging
from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge
from upload_api import validate_excel, MAX_BYTES
from invoice_import_preview import build_preview
from payment_evidence_contract import preview_payment_rows, FIXED_PAYMENT_HEADERS

MAX_ROWS=20000

def _reply(payload,status=200):
    result=jsonify(payload)
    result.status_code=status
    result.headers["Cache-Control"]="no-store"
    result.headers["X-Content-Type-Options"]="nosniff"
    result.headers["Pragma"]="no-cache"
    return result

def _read_upload():
    request.max_content_length=MAX_BYTES+65536
    if request.content_length is None:
        raise ValueError("CONTENT_LENGTH_REQUIRED")
    if request.content_length>MAX_BYTES+65536:
        raise RequestEntityTooLarge()
    if request.mimetype!="multipart/form-data":
        raise ValueError("MULTIPART_REQUIRED")
    upload=request.files.getlist("file")
    if len(upload)!=1 or len(request.files)!=1 or request.form:
        raise ValueError("ONE_FILE_ONLY")
    file=upload[0]
    raw=file.stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise RequestEntityTooLarge()
    validate_excel(file.filename,raw)
    return file.filename,raw

def _payment_rows_xlsx(data):
    """Three-column standalone evidence; not the original PAYMNENT A-L ledger."""
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=False)
    try:
        if len(book.worksheets)!=1:
            raise ValueError("PAYMENT_ONE_SHEET_REQUIRED")
        sheet=book.worksheets[0]
        if sheet.max_column!=3 or sheet.max_row>MAX_ROWS+1:
            raise ValueError("PAYMENT_EXACT_3_COLUMNS_MAX_20000_ROWS")
        iterator=sheet.iter_rows(min_col=1,max_col=3)
        headers=[x.value for x in next(iterator,[])]
        if tuple(headers)!=FIXED_PAYMENT_HEADERS:
            raise ValueError("PAYMENT_EXACT_HEADERS_REQUIRED")
        rows=[]
        for source_row,cells in enumerate(iterator,start=2):
            if len(rows)>=MAX_ROWS:
                raise ValueError("PAYMENT_ROW_LIMIT")
            converted=[]
            for cell in cells:
                # Financial data cells must be originally typed as Excel TEXT.
                # Never silently reformat numeric SOL IDs (leading zeros).
                if cell.value is None:
                    converted.append("")
                elif cell.data_type=="s" and isinstance(cell.value,str):
                    converted.append(cell.value)
                else:
                    converted.append(None)
            rows.append(converted)
        return rows
    finally:
        book.close()

def create_private_preview_blueprint(*,auth_guard=None,csrf_guard=None):
    """Inject trusted request-context callbacks. Production registration forbidden
    until independent Firebase/CSRF parity, mapping and owner release review.
    """
    bp=Blueprint("stage31_4_private_preview",__name__,url_prefix="/__stage31_4")

    @bp.before_request
    def secure_private_routes():
        if current_app.config.get("SBI_STAGE31_4_PRIVATE_ENABLED") is not True:
            return _reply({"error":"Not found"},404)
        # Default deny. Actual verified Firebase cookie/session context must
        # be supplied server-side, not a browser-provided identity header.
        if not callable(auth_guard) or not callable(csrf_guard):
            return _reply({"error":"Private integration not configured"},503)
        try:
            authenticated=auth_guard() is True
        except Exception:
            logging.exception("Stage31.4 authentication verifier failed")
            return _reply({"error":"Authentication unavailable"},503)
        if not authenticated:
            return _reply({"error":"Login required"},401)
        try:
            valid_csrf=csrf_guard() is True
        except Exception:
            logging.exception("Stage31.4 CSRF verifier failed")
            return _reply({"error":"CSRF unavailable"},503)
        if not valid_csrf:
            return _reply({"error":"CSRF verification required"},403)

    @bp.route("/<kind>/preview",methods=["POST"])
    def preview(kind):
        if kind not in ("invoice","payment"):
            return _reply({"error":"Unknown intake type"},404)
        try:
            filename,data=_read_upload()
            checksum=hashlib.sha256(data).hexdigest()
            if kind=="invoice":
                # Source only: NO authoritative live invoice uniqueness lookup,
                # verified client mapping, branch ID or source-row FK yet.
                result=build_preview(filename,data,existing_invoices=())
                return _reply({
                    "contract":"STAGE31_4_INVOICE_SOURCE_PREVIEW_ONLY",
                    "status":"REVIEW_REQUIRED_NO_DATABASE_WRITE",
                    "source_sha256":checksum,
                    "source_column_count":len(result["headers"]),
                    "source_sheet":result["sheet"],
                    "total":result["summary"]["total"],
                    "source_contract_ready_count":result["summary"]["ready_to_add"],
                    "source_rejected_count":result["summary"]["rejected"],
                    "production_uniqueness_checked":False,
                    "branch_sol_master_mapping_verified":False,
                    "source_row_fk_bound":False,
                    "financial_engine_enabled":False,
                    "database_changed":False,
                })
            if not filename.lower().endswith(".xlsx"):
                return _reply({"error":"PAYMENT_EVIDENCE_REQUIRES_XLSX"},415)
            rows=_payment_rows_xlsx(data)
            check=preview_payment_rows(FIXED_PAYMENT_HEADERS,rows)
            return _reply({
                "contract":"STAGE31_4_PAYMENT_EVIDENCE_PREVIEW_ONLY",
                "status":"REVIEW_REQUIRED_NO_DATABASE_WRITE",
                "source_sha256":checksum,
                "total":check["total"],
                "source_contract_ready_count":check["ready_for_source_review"],
                "source_rejected_count":check["rejected"],
                "bank_transaction_identity_verified":False,
                "original_payment_A_to_L_mapped":False,
                "financial_engine_enabled":False,
                "database_changed":False,
            })
        except RequestEntityTooLarge:
            return _reply({"error":"Maximum file size is 8 MiB"},413)
        except ValueError as exc:
            return _reply({"error":str(exc)},400)
        except Exception:
            # Do not expose source rows, traces, invoice values or credentials.
            logging.exception("Stage31.4 preview rejected")
            return _reply({"error":"Preview unavailable; review source contract"},422)

    @bp.route("/<kind>/apply",methods=["POST"])
    def apply_locked(kind):
        # Even valid synthetic sessions must never enable a financial write.
        if kind not in ("invoice","payment"):
            return _reply({"error":"Unknown intake type"},404)
        return _reply({
            "error":"STAGE31_4_APPLY_LOCKED_PENDING_STAGE31_5_OWNER_APPROVAL",
            "financial_engine_enabled":False,
            "database_changed":False,
        },423)

    return bp
