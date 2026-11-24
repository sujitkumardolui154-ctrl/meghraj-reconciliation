"""Authenticated invoice generation and GST XLSX routes for SBI Workspace.

Feature-disabled by default; no payment/reconciliation allocation code imports.
All writes are confined to sbi_invoice_gst.invoices and invoice_lines.
"""
from datetime import date
from io import BytesIO
import json
import os
import re

from flask import Blueprint, Response, g, jsonify, request

from invoice_gst_core import (
    HEADERS, InvoiceError, build_invoice, financial_year, gst_row,
    safe_excel_cell,
)

MAX_BYTES = 2 * 1024 * 1024
MAX_EXPORT_ROWS = 20000


def connect_private_db():
    url = os.environ.get("SBI_INVOICE_GST_DATABASE_URL", "")
    if not url:
        raise RuntimeError("ISOLATED_INVOICE_DATABASE_NOT_CONFIGURED")
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=6,
                           options="-c statement_timeout=20000")


def create_invoice_gst_blueprint(can_read, can_create, csrf_valid,
                                 connection_factory=None):
    blueprint = Blueprint("sbi_invoice_gst", __name__, url_prefix="/api/invoice-gst")
    connect = connection_factory or connect_private_db

    def failure(message, status):
        return jsonify(error=message, financial_execution_enabled=False), status

    def private_db():
        try:
            return connect()
        except Exception:
            raise RuntimeError("INVOICE_DATABASE_UNAVAILABLE") from None

    @blueprint.before_request
    def check_access():
        if os.environ.get("SBI_INVOICE_GST_ENABLED") != "1":
            return failure("INVOICE_GST_FEATURE_NOT_ENABLED", 503)
        if request.method not in ("GET", "POST"):
            return failure("METHOD_NOT_ALLOWED", 405)
        if request.method == "POST":
            if not can_create():
                return failure("INVOICE_CREATOR_PERMISSION_REQUIRED", 403)
            if not csrf_valid():
                return failure("CSRF_VERIFICATION_FAILED", 403)
        elif not (can_read() or can_create()):
            return failure("INVOICE_REPORT_VIEWER_PERMISSION_REQUIRED", 403)

    @blueprint.get("/branches")
    def branches():
        query = request.args.get("search", "").strip()
        if len(query) > 80 or any(ord(x) < 32 for x in query):
            return failure("INVALID_BRANCH_SEARCH", 400)
        try:
            with private_db() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT branch_key, client_name, sol_id, invoice_branch
                       FROM sbi_invoice_gst.verified_branches
                       WHERE verified = TRUE AND client_name ILIKE %s
                       ORDER BY client_name, sol_id LIMIT 50""",
                    ("%" + query + "%",),
                )
                rows = cur.fetchall()
            return jsonify(branches=rows, count=len(rows))
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE", 503)

    def read_branch(conn, branch_key):
        with conn.cursor() as cur:
            cur.execute(
                """SELECT branch_key, client_name, invoice_branch,
                          invoice_generate_location, original_branch_name,
                          sol_id, client_class, gstin, recipient_title,
                          customer_address, state_code, verified
                   FROM sbi_invoice_gst.verified_branches
                   WHERE branch_key = %s AND verified = TRUE""",
                (branch_key,),
            )
            return cur.fetchone()

    def validate_request():
        if request.content_length and request.content_length > MAX_BYTES:
            raise InvoiceError("INVOICE_PAYLOAD_TOO_LARGE")
        if not request.is_json:
            raise InvoiceError("JSON_REQUEST_REQUIRED")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InvoiceError("INVALID_JSON")
        branch_key = payload.get("branch_key")
        if not isinstance(branch_key, str) or not 1 <= len(branch_key) <= 100:
            raise InvoiceError("INVALID_BRANCH_KEY")
        return payload, branch_key

    @blueprint.post("/preview")
    def preview():
        try:
            payload, key = validate_request()
            with private_db() as conn:
                branch = read_branch(conn, key)
            invoice = build_invoice(payload, branch)
            # Do not place the untrusted submitted annexure into logs.
            invoice.pop("shipments")
            return jsonify(invoice=invoice, persistence="NONE",
                           financial_writes=False)
        except InvoiceError as exc:
            return failure(str(exc), 422)
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE", 503)

    @blueprint.post("/finalize")
    def finalize():
        if os.environ.get("SBI_INVOICE_GST_FINALIZE_ENABLED") != "1":
            return failure("INVOICE_FINALIZATION_LOCKED", 403)
        if os.environ.get("SBI_INVOICE_GST_DEPLOYMENT_MODE") not in ("ISOLATED_QA", "APPROVED_LIVE"):
            return failure("INVOICE_DATABASE_MODE_UNAPPROVED", 403)
        user_uid = getattr(getattr(g, "dil_user", None), "uid", None)
        if not isinstance(user_uid, str) or not user_uid:
            return failure("AUTHENTICATED_INVOICE_OWNER_REQUIRED", 403)
        try:
            payload, key = validate_request()
            with private_db() as conn:
                branch = read_branch(conn, key)
                invoice = build_invoice(payload, branch)
                # Exact source logo/company details must be approved privately
                # before permitting finalized invoices.
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT 1 FROM sbi_invoice_gst.vendor_profiles
                           WHERE vendor_key='MEGHRAJ_EXPRESS'
                             AND exact_logo_verified = TRUE
                             AND logo_image IS NOT NULL
                             AND length(logo_image) > 0
                             AND verified_by IS NOT NULL
                             AND verified_at IS NOT NULL
                           LIMIT 1"""
                    )
                    if cur.fetchone() is None:
                        return failure("ORIGINAL_LOGO_AND_VENDOR_PROFILE_NOT_APPROVED", 409)
                from psycopg.types.json import Jsonb
                from psycopg.errors import UniqueViolation
                try:
                    with conn.transaction():
                        with conn.cursor() as cur:
                            cur.execute(
                                """INSERT INTO sbi_invoice_gst.invoices
                                (invoice_no, branch_key, service_from, service_to,
                                 invoice_date, service_month, service_month_key, fy,
                                 invoice_branch, invoice_generate_location,
                                 original_branch_name, sol_id, client_name, gstin,
                                 master_snapshot, taxable, cgst, sgst, total,
                                 shipment_count, created_by_uid)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (
                                    invoice["invoice_no"], key,
                                    invoice["service_from"], invoice["service_to"],
                                    invoice["invoice_date"], invoice["service_month"],
                                    invoice["service_month_key"], invoice["fy"],
                                    invoice["invoice_branch"],
                                    invoice["invoice_generate_location"],
                                    invoice["original_branch_name"], invoice["sol_id"],
                                    invoice["client_name"], invoice["gstin"],
                                    Jsonb({k: v for k, v in invoice.items() if k != "shipments"}),
                                    invoice["taxable"], invoice["cgst"], invoice["sgst"],
                                    invoice["total"], invoice["shipment_count"], user_uid,
                                ),
                            )
                            cur.executemany(
                                """INSERT INTO sbi_invoice_gst.invoice_lines
                                   (invoice_no,line_no,dispatch_date,lr_no,
                                    packet_ref_no,consignee,weight_kg,amount)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                                [
                                    (invoice["invoice_no"], line["line_no"],
                                     line["dispatch_date"], line["lr_no"],
                                     line["packet_ref_no"], line["consignee"],
                                     line["weight_kg"], line["amount"])
                                    for line in invoice["shipments"]
                                ],
                            )
                except UniqueViolation:
                    return failure("DUPLICATE_INVOICE_NUMBER_NO_SECOND_WRITE", 409)
            return jsonify(
                status="FINALIZED", invoice_no=invoice["invoice_no"],
                shipment_count=invoice["shipment_count"], total=invoice["total"],
                database_recorded=True, reconciliation_applied=False,
                financial_execution_enabled=False,
            ), 201
        except InvoiceError as exc:
            return failure(str(exc), 422)
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE_OR_WRITE_REJECTED", 503)

    @blueprint.get("/invoices/<invoice_no>")
    def get_invoice(invoice_no):
        if re.fullmatch(r"MXP[0-9]{4,10}", invoice_no) is None:
            return failure("INVALID_INVOICE_NUMBER", 400)
        try:
            with private_db() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT invoice_no, branch_key, service_from::text AS service_from,
                              service_to::text AS service_to, invoice_date::text AS invoice_date,
                              service_month, fy, invoice_branch, invoice_generate_location,
                              original_branch_name, sol_id, client_name, gstin,
                              taxable::text AS taxable, cgst::text AS cgst,
                              sgst::text AS sgst, total::text AS total,
                              shipment_count, status, created_at::text AS created_at
                       FROM sbi_invoice_gst.invoices WHERE invoice_no=%s""",
                    (invoice_no,),
                )
                row = cur.fetchone()
            if row is None:
                return failure("INVOICE_NOT_FOUND", 404)
            return jsonify(invoice=row, reconciliation_applied=False)
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE", 503)

    @blueprint.get("/gst.xlsx")
    def gst_excel():
        if not can_read():
            return failure("GST_REPORT_VIEWER_PERMISSION_REQUIRED", 403)
        month = request.args.get("month", "")
        if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) is None:
            return failure("INVALID_SERVICE_MONTH", 400)
        year_start = financial_year(date.fromisoformat(month + "-01"))
        if request.args.get("fy", year_start) != year_start:
            return failure("FY_SERVICE_MONTH_CONFLICT", 422)
        try:
            with private_db() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT invoice_no, service_month, fy,
                              invoice_branch, invoice_generate_location,
                              invoice_date::text AS invoice_date,
                              original_branch_name, sol_id, client_name, gstin,
                              taxable::text AS taxable, cgst::text AS cgst,
                              sgst::text AS sgst, total::text AS total,
                              status, verification_flags
                       FROM sbi_invoice_gst.invoices
                       WHERE service_month_key=%s AND fy=%s
                             AND status='FINALIZED'
                       ORDER BY invoice_no LIMIT %s""",
                    (month, year_start, MAX_EXPORT_ROWS + 1),
                )
                rows = cur.fetchall()
            if len(rows) > MAX_EXPORT_ROWS:
                return failure("EXPORT_TOO_LARGE_USE_BOUNDED_FILTER", 413)
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "GST Report"
            sheet.append(HEADERS)
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="17365D")
            for record in rows:
                values = gst_row(record)
                sheet.append([
                    float(values[i]) if i in (10,11,12,13) else safe_excel_cell(values[i])
                    for i in range(len(HEADERS))
                ])
            for row in sheet.iter_rows(min_row=2):
                for idx in (5,7):
                    row[idx].number_format = "@"
                for idx in (10,11,12,13):
                    row[idx].number_format = '#,##0.00'
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            output = BytesIO()
            workbook.save(output)
            response = Response(
                output.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response.headers["Content-Disposition"] = (
                'attachment; filename="SBI-GST-' + month + '.xlsx"'
            )
            response.headers["X-Report-Rows"] = str(len(rows))
            response.headers["X-GST-Contract-Columns"] = str(len(HEADERS))
            response.headers["X-Reconciliation-Executed"] = "false"
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except InvoiceError as exc:
            return failure(str(exc), 422)
        except Exception:
            return failure("GST_REPORT_DATABASE_UNAVAILABLE", 503)

    return blueprint
