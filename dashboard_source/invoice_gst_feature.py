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
                       WHERE verified = TRUE AND (
                         client_name ILIKE %s
                         OR sol_id ILIKE %s
                         OR invoice_branch ILIKE %s
                       )
                       ORDER BY client_name, sol_id LIMIT 50""",
                    ("%" + query + "%", "%" + query + "%",
                     "%" + query + "%"),
                )
                rows = cur.fetchall()
            return jsonify(branches=rows, count=len(rows))
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE", 503)

    @blueprint.post("/annexure/parse")
    def parse_excel_annexure():
        """Upload/normalize ONLY in memory; no DB insert or payment writes."""
        from invoice_annexure_intake import (
            AnnexureImportError, MAX_FILE_BYTES, parse_xlsx_annexure,
        )
        if request.content_length and request.content_length > MAX_FILE_BYTES + 16384:
            return failure("EXCEL_FILE_SIZE_LIMIT", 413)
        upload = request.files.get("file")
        if not upload or not isinstance(upload.filename, str) or not (
            upload.filename.lower().endswith(".xlsx")
        ):
            return failure("XLSX_FILE_REQUIRED", 422)
        try:
            raw = upload.stream.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                return failure("EXCEL_FILE_SIZE_LIMIT", 413)
            info = parse_xlsx_annexure(raw)
            response = jsonify(info)
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except AnnexureImportError as exc:
            return failure(str(exc), 422)
        except Exception:
            return failure("EXCEL_ANNEXURE_PARSER_UNAVAILABLE", 503)

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
                with conn.cursor() as cur:
                    number = payload.get("invoice_no")
                    if isinstance(number, str) and re.fullmatch(r"MXP[0-9]{4,10}", number):
                        cur.execute(
                            """SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations
                               WHERE invoice_no=%s""", (number,),
                        )
                        if cur.fetchone() is not None:
                            return failure("CANCELLED_INVOICE_NUMBER_CANNOT_BE_REUSED", 409)
            invoice = build_invoice(payload, branch)
            # A correction is a review-only copy, not a replacement invoice.
            correction_source = payload.get("replaces_invoice_no")
            if correction_source is not None:
                if not isinstance(correction_source, str) or re.fullmatch(
                    r"MXP[0-9]{4,10}", correction_source
                ) is None or correction_source == invoice["invoice_no"]:
                    return failure("INVALID_CORRECTION_SOURCE_NUMBER", 422)
                # The preceding branch lookup context has ended. Re-open an
                # isolated read-only verification context instead of using
                # a closed connection for the correction source.
                with private_db() as correction_conn, correction_conn.cursor() as cur:
                    cur.execute(
                        """SELECT i.status,
                                  EXISTS (
                                      SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations c
                                      WHERE c.invoice_no=i.invoice_no
                                  ) AS cancelled
                           FROM sbi_invoice_gst.invoices i
                           WHERE i.invoice_no=%s""",
                        (correction_source,),
                    )
                    original = cur.fetchone()
                if not original or original["status"] != "FINALIZED" or original["cancelled"]:
                    return failure("CORRECTION_SOURCE_NOT_VERIFIED_FINALIZED", 409)
                invoice["correction_review_only"] = True
                invoice["correction_source_invoice_no"] = correction_source
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
            if payload.get("replaces_invoice_no") is not None:
                return failure("CORRECTION_REQUIRES_APPROVED_REVISION_WORKFLOW", 403)
            with private_db() as conn:
                branch = read_branch(conn, key)
                invoice = build_invoice(payload, branch)
                if (invoice["multi_month_period"]
                        and os.environ.get("SBI_INVOICE_GST_DEPLOYMENT_MODE") != "ISOLATED_QA"):
                    return failure("MULTI_MONTH_GST_PERIOD_POLICY_NOT_APPROVED", 403)
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
                             AND registered_office IS NOT NULL AND length(registered_office)>0
                             AND registered_phone IS NOT NULL AND length(registered_phone)>0
                             AND registered_email IS NOT NULL AND length(registered_email)>0
                             AND head_office IS NOT NULL AND length(head_office)>0
                             AND head_phone IS NOT NULL AND length(head_phone)>0
                             AND website IS NOT NULL AND length(website)>0
                           LIMIT 1"""
                    )
                    if cur.fetchone() is None:
                        return failure("ORIGINAL_LOGO_AND_VENDOR_PROFILE_NOT_APPROVED", 409)
                from psycopg.types.json import Jsonb
                from psycopg.errors import UniqueViolation
                try:
                    with conn.transaction():
                        with conn.cursor() as cur:
                            # Shares the same invoice-number advisory lock as
                            # the append-only void/cancellation endpoint.
                            cur.execute(
                                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                                (invoice["invoice_no"],),
                            )
                            cur.execute(
                                """SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations
                                   WHERE invoice_no=%s""", (invoice["invoice_no"],),
                            )
                            if cur.fetchone() is not None:
                                return failure("CANCELLED_INVOICE_NUMBER_CANNOT_BE_REUSED", 409)
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
        """Return a finalized invoice and, when requested, all original AWBs.

        This is an immutable source read. Correction copies are never saved
        back to this number; a separately approved revision flow is required.
        """
        if re.fullmatch(r"MXP[0-9]{4,10}", invoice_no) is None:
            return failure("INVALID_INVOICE_NUMBER", 400)
        include_lines = request.args.get("include_lines", "0")
        if include_lines not in ("0", "1"):
            return failure("INVALID_INVOICE_LOOKUP_OPTIONS", 400)
        try:
            with private_db() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT invoice_no, branch_key, service_from::text AS service_from,
                              service_to::text AS service_to, invoice_date::text AS invoice_date,
                              service_month, service_month_key, fy,
                              invoice_branch, invoice_generate_location,
                              original_branch_name, sol_id, client_name, gstin,
                              taxable::text AS taxable, cgst::text AS cgst,
                              sgst::text AS sgst, total::text AS total,
                              shipment_count, verification_flags,
                              CASE WHEN EXISTS (
                                  SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations c
                                  WHERE c.invoice_no = i.invoice_no
                              ) THEN 'CANCELLED' ELSE status END AS status,
                              created_at::text AS created_at
                       FROM sbi_invoice_gst.invoices i WHERE invoice_no=%s""",
                    (invoice_no,),
                )
                row = cur.fetchone()
                if row is None:
                    return failure("INVOICE_NOT_FOUND", 404)
                lines = None
                if include_lines == "1":
                    cur.execute(
                        """SELECT line_no, dispatch_date::text AS dispatch_date,
                                  lr_no, packet_ref_no, consignee,
                                  weight_kg::text AS weight_kg,
                                  amount::text AS amount
                           FROM sbi_invoice_gst.invoice_lines
                           WHERE invoice_no=%s ORDER BY line_no""",
                        (invoice_no,),
                    )
                    lines = cur.fetchall()
                    if len(lines) != row["shipment_count"]:
                        return failure("INVOICE_ANNEXURE_INTEGRITY_REVIEW_REQUIRED", 409)
            result = {
                "invoice": row, "reconciliation_applied": False,
                "original_immutable": True,
                "correction_requires_separate_approval": True,
            }
            if lines is not None:
                result["shipments"] = lines
            response = jsonify(result)
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except Exception:
            return failure("INVOICE_DATABASE_UNAVAILABLE", 503)

    @blueprint.get("/invoices/<invoice_no>.pdf")
    def invoice_pdf(invoice_no):
        """Render from immutable, finalized registry and private vendor logo."""
        if not (can_read() or can_create()):
            return failure("INVOICE_PDF_VIEWER_PERMISSION_REQUIRED", 403)
        if re.fullmatch(r"MXP[0-9]{4,10}", invoice_no) is None:
            return failure("INVALID_INVOICE_NUMBER", 400)
        try:
            from invoice_gst_pdf import render_invoice_pdf, TemplateVerificationError
            with private_db() as conn, conn.cursor() as cur:
                cur.execute(
                    """SELECT invoice_no, service_from::text AS service_from,
                              service_to::text AS service_to,
                              invoice_date::text AS invoice_date,
                              service_month, service_month_key, fy, client_name,
                              gstin, invoice_branch, invoice_generate_location,
                              original_branch_name, sol_id, master_snapshot,
                              taxable::text AS taxable, cgst::text AS cgst,
                              sgst::text AS sgst, total::text AS total,
                              shipment_count, status, verification_flags
                       FROM sbi_invoice_gst.invoices
                       WHERE invoice_no = %s""",
                    (invoice_no,),
                )
                invoice = cur.fetchone()
                if invoice is None:
                    return failure("INVOICE_NOT_FOUND", 404)
                cur.execute(
                    """SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations
                       WHERE invoice_no=%s""", (invoice_no,),
                )
                if cur.fetchone() is not None:
                    return failure("CANCELLED_INVOICE_PDF_NOT_ACTIVE", 409)
                cur.execute(
                    """SELECT line_no, dispatch_date::text AS dispatch_date,
                              lr_no, packet_ref_no, consignee,
                              weight_kg::text AS weight_kg,
                              amount::text AS amount
                       FROM sbi_invoice_gst.invoice_lines
                       WHERE invoice_no = %s ORDER BY line_no""",
                    (invoice_no,),
                )
                lines = cur.fetchall()
                cur.execute(
                    """SELECT legal_name, logo_image, logo_mime,
                              exact_logo_verified, declaration_text,
                              bank_instructions, pan, gstin, vendor_id,
                              service_type, sac_code, footer_text,
                              authorized_signature_label, verified_by, verified_at,
                              registered_office, registered_phone, registered_email,
                              head_office, head_phone, website
                       FROM sbi_invoice_gst.vendor_profiles
                       WHERE vendor_key = 'MEGHRAJ_EXPRESS'""",
                )
                profile = cur.fetchone()
            if not profile:
                return failure("VENDOR_PROFILE_UNAVAILABLE", 409)
            try:
                document = render_invoice_pdf(invoice, profile, lines)
            except TemplateVerificationError:
                return failure("PDF_TEMPLATE_OR_SOURCE_VERIFICATION_REQUIRED", 409)
            response = Response(document, content_type="application/pdf")
            response.headers["Content-Disposition"] = (
                'attachment; filename="Meghraj-' + invoice_no + '.pdf"'
            )
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        except Exception:
            return failure("INVOICE_PDF_SOURCE_UNAVAILABLE", 503)

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
                # An invoice spanning Sept-Oct must not silently enter only
                # September GST, nor be duplicated in October. Until an
                # accounting policy allocates the service period, block the
                # affected monthly report rather than misrepresenting it.
                cur.execute(
                    """SELECT 1 FROM sbi_invoice_gst.invoices i
                       WHERE i.status='FINALIZED'
                         AND date_trunc('month',i.service_from)
                             <> date_trunc('month',i.service_to)
                         AND i.service_from < (CAST(%s AS date) + INTERVAL '1 month')
                         AND i.service_to >= CAST(%s AS date)
                         AND NOT EXISTS (
                             SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations c
                             WHERE c.invoice_no=i.invoice_no
                         )
                       LIMIT 1""",
                    (month + "-01", month + "-01"),
                )
                if cur.fetchone() is not None:
                    return failure("MULTI_MONTH_GST_REPORT_PERIOD_POLICY_PENDING", 409)
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
                             AND NOT EXISTS (
                                 SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations c
                                 WHERE c.invoice_no=sbi_invoice_gst.invoices.invoice_no
                             )
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
