"""Invoice number void / cancellation log. Isolated PostgreSQL QA only.

Original finalized invoices and shipment lines remain immutable. An append-only
cancellation record determines effective status. This never reverses payment,
GST filing, reconciliation or credit-note ledger entries.
"""
import os
import re

from flask import Blueprint, g, jsonify, request

from invoice_gst_feature import connect_private_db

INVOICE_PATTERN = re.compile(r"MXP[0-9]{4,10}\Z")
REASONS = {"NUMBER_UNUSED", "ENTRY_ERROR", "CUSTOMER_REQUEST",
           "DUPLICATE_REQUEST", "OTHER"}


def create_invoice_cancellation_blueprint(can_read, can_cancel, csrf_valid,
                                          connection_factory=None):
    bp = Blueprint("sbi_invoice_cancellation", __name__,
                   url_prefix="/api/invoice-gst")
    connect = connection_factory or connect_private_db

    def fail(code, status):
        return jsonify(error=code, financial_execution_enabled=False), status

    @bp.before_request
    def check_access():
        if os.environ.get("SBI_INVOICE_GST_ENABLED") != "1":
            return fail("INVOICE_GST_FEATURE_NOT_ENABLED", 503)
        if request.method == "POST":
            if not can_cancel():
                return fail("INVOICE_CANCELLER_PERMISSION_REQUIRED", 403)
            if not csrf_valid():
                return fail("CSRF_VERIFICATION_FAILED", 403)
        elif not (can_cancel() or can_read()):
            return fail("INVOICE_CANCELLATION_VIEWER_PERMISSION_REQUIRED", 403)

    @bp.get("/cancellations")
    def list_cancellations():
        invoice_no = request.args.get("invoice_no", "").strip()
        if invoice_no and not INVOICE_PATTERN.fullmatch(invoice_no):
            return fail("INVALID_INVOICE_NUMBER", 400)
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT invoice_no, cancellation_kind, reason_code,
                                  reason_text, review_reference, cancelled_by_uid,
                                  cancelled_at::text AS cancelled_at,
                                  source_financial_snapshot
                           FROM sbi_invoice_gst.invoice_number_cancellations
                           WHERE (%s = '' OR invoice_no = %s)
                           ORDER BY cancelled_at DESC, invoice_no LIMIT 200""",
                        (invoice_no, invoice_no),
                    )
                    records = cur.fetchall()
            return jsonify(records=records, count=len(records), financial_writes=False)
        except Exception:
            return fail("CANCELLATION_REGISTER_UNAVAILABLE", 503)

    @bp.post("/cancellations")
    def create_cancellation():
        # Explicitly QA ONLY: no verified check of historical financial
        # posting, GST filing or reconciliation is yet wired to this module.
        if os.environ.get("SBI_INVOICE_GST_CANCELLATION_ENABLED") != "1":
            return fail("INVOICE_CANCELLATION_LOCKED", 403)
        if os.environ.get("SBI_INVOICE_GST_DEPLOYMENT_MODE") != "ISOLATED_QA":
            return fail("LIVE_CANCELLATION_REQUIRES_EXTERNAL_LEDGER_INTEGRATION", 403)
        uid = getattr(getattr(g, "dil_user", None), "uid", None)
        if not isinstance(uid, str) or not uid:
            return fail("AUTHENTICATED_INVOICE_OWNER_REQUIRED", 403)
        if request.content_length and request.content_length > 16384:
            return fail("CANCELLATION_PAYLOAD_TOO_LARGE", 413)
        if not request.is_json:
            return fail("JSON_REQUEST_REQUIRED", 400)
        p = request.get_json(silent=True)
        if not isinstance(p, dict):
            return fail("INVALID_JSON", 400)
        invoice_no = p.get("invoice_no")
        reason_code = p.get("reason_code")
        reason = p.get("reason")
        review = p.get("review_reference")
        if not isinstance(invoice_no, str) or not INVOICE_PATTERN.fullmatch(invoice_no):
            return fail("INVALID_INVOICE_NUMBER", 422)
        if reason_code not in REASONS:
            return fail("INVALID_CANCELLATION_REASON_CODE", 422)
        if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
            return fail("CANCELLATION_REASON_REQUIRED", 422)
        if any(ord(c) < 32 for c in reason):
            return fail("INVALID_CANCELLATION_REASON", 422)
        if review is not None and (
            not isinstance(review, str) or len(review) > 120
            or any(ord(c) < 32 for c in review)
        ):
            return fail("INVALID_REVIEW_REFERENCE", 422)
        try:
            from psycopg.types.json import Jsonb
            with connect() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        dbname = conn.execute(
                            "SELECT current_database() AS db"
                        ).fetchone()["db"]
                        if dbname != "invoice_qa":
                            return fail("REFUSE_NON_ISOLATED_QA_DATABASE", 403)
                        # Finalize also takes the same transaction advisory
                        # lock. This prevents void-vs-finalize races.
                        cur.execute(
                            "SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (invoice_no,),
                        )
                        cur.execute(
                            """SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations
                               WHERE invoice_no=%s""", (invoice_no,),
                        )
                        if cur.fetchone() is not None:
                            return fail("INVOICE_NUMBER_ALREADY_CANCELLED", 409)
                        cur.execute(
                            """SELECT invoice_no, status, invoice_date::text AS invoice_date,
                                      service_month_key, branch_key, taxable::text AS taxable,
                                      cgst::text AS cgst, sgst::text AS sgst,
                                      total::text AS total
                               FROM sbi_invoice_gst.invoices
                               WHERE invoice_no=%s FOR SHARE""",
                            (invoice_no,),
                        )
                        invoice = cur.fetchone()
                        kind = "CANCEL_FINALIZED" if invoice else "VOID_UNUSED"
                        if invoice:
                            if not isinstance(review, str) or not 6 <= len(review.strip()) <= 120:
                                return fail("FINALIZED_INVOICE_REVIEW_REFERENCE_REQUIRED", 422)
                            if p.get("accounting_review_confirmed") is not True:
                                return fail("ACCOUNTING_REVIEW_CONFIRMATION_REQUIRED", 422)
                        elif reason_code != "NUMBER_UNUSED":
                            return fail("UNUSED_INVOICE_NUMBER_REASON_REQUIRED", 422)
                        cur.execute(
                            """INSERT INTO sbi_invoice_gst.invoice_number_cancellations
                               (invoice_no, cancellation_kind, finalized_invoice_no,
                                reason_code, reason_text, review_reference,
                                cancelled_by_uid, source_financial_snapshot)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (invoice_no, kind, invoice_no if invoice else None,
                             reason_code, reason.strip(),
                             review.strip() if invoice else None, uid,
                             Jsonb(dict(invoice)) if invoice else None),
                        )
            return jsonify(
                invoice_no=invoice_no, status="CANCELLED", cancellation_kind=kind,
                audit_logged=True, accounting_reversal_performed=False,
                reconciliation_applied=False, financial_execution_enabled=False,
            ), 201
        except Exception:
            return fail("CANCELLATION_DATABASE_UNAVAILABLE_OR_CONFLICT", 503)

    return bp
