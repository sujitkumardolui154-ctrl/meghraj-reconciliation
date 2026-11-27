"""Authenticated isolated credit-note generation; never mutates reconciliation.

Source invoice details are loaded from PostgreSQL, not from user input.
Only the existing isolated invoice_qa registry is supported currently.
Historical reconciled invoices need a separately verified read-only adapter.
"""
from flask import Blueprint, Response, g, jsonify, request
import os
import re

from credit_note_core import CreditNoteError, credit_note_request, build_credit_note
from credit_note_pdf import render_credit_note_pdf
from invoice_gst_feature import connect_private_db

CN_NUMBER = re.compile(r"MXP/[0-9]{4}-[0-9]{4}/[0-9]{1,6}\Z")
INVOICE_NUMBER = re.compile(r"MXP[0-9]{4,10}\Z")

SOURCE_SQL = """
SELECT invoice_no, branch_key, invoice_date::text AS invoice_date,
       service_month, sol_id, client_name, gstin, master_snapshot,
       taxable::text AS taxable, status, verification_flags,
       EXISTS(
           SELECT 1 FROM sbi_invoice_gst.invoice_number_cancellations c
           WHERE c.invoice_no=i.invoice_no
       ) AS cancelled
FROM sbi_invoice_gst.invoices i WHERE invoice_no = ANY(%s)
"""


def create_credit_note_blueprint(can_read, can_create, csrf_valid,
                                 connection_factory=None):
    bp = Blueprint("sbi_credit_note_generation", __name__,
                   url_prefix="/api/credit-notes")
    connect = connection_factory or connect_private_db

    def fail(message, status):
        return jsonify(error=message, ledger_posted=False,
                       financial_execution_enabled=False), status

    @bp.before_request
    def guard():
        if os.environ.get("SBI_CREDIT_NOTE_ENABLED") != "1":
            return fail("CREDIT_NOTE_FEATURE_DISABLED", 503)
        if request.method == "POST":
            if not can_create():
                return fail("CREDIT_NOTE_CREATOR_PERMISSION_REQUIRED", 403)
            if not csrf_valid():
                return fail("CSRF_VERIFICATION_FAILED", 403)
        elif not (can_read() or can_create()):
            return fail("CREDIT_NOTE_VIEWER_PERMISSION_REQUIRED", 403)

    def parse_body():
        if request.content_length and request.content_length > 256 * 1024:
            raise CreditNoteError("CREDIT_NOTE_PAYLOAD_TOO_LARGE")
        if not request.is_json:
            raise CreditNoteError("JSON_REQUIRED")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise CreditNoteError("INVALID_REQUEST")
        return body

    def invoice_sources(conn, numbers):
        with conn.cursor() as cur:
            cur.execute(SOURCE_SQL, (numbers,))
            rows = cur.fetchall()
            cur.execute(
                """SELECT invoice_no, credited_taxable::text AS amount
                   FROM sbi_invoice_gst.credit_note_invoice_credits
                   WHERE invoice_no=ANY(%s)""",
                (numbers,),
            )
            prior = {row["invoice_no"]: row["amount"] for row in cur.fetchall()}
        return {r["invoice_no"]: r for r in rows}, prior

    def vendor_profile(conn):
        with conn.cursor() as cur:
            cur.execute(
                """SELECT legal_name, logo_image, logo_mime,
                          exact_logo_verified, declaration_text,
                          bank_instructions, pan, gstin, vendor_id,
                          service_type, sac_code, footer_text,
                          authorized_signature_label, verified_by, verified_at,
                          registered_office, registered_phone, registered_email,
                          head_office, head_phone, website
                   FROM sbi_invoice_gst.vendor_profiles
                   WHERE vendor_key='MEGHRAJ_EXPRESS'
                     AND exact_logo_verified=TRUE""",
            )
            return cur.fetchone()

    def check_note_numbers(conn, note_no):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM sbi_invoice_gst.credit_notes WHERE credit_note_no=%s",
                (note_no,),
            )
            if cur.fetchone() is not None:
                raise CreditNoteError("DUPLICATE_CREDIT_NOTE_NUMBER")

    def prepared(conn, data):
        req = credit_note_request(data)
        numbers = [x["invoice_no"] for x in req["entries"]]
        invoices, earlier = invoice_sources(conn,numbers)
        return build_credit_note(data,invoices,earlier)

    @bp.post("/lookup")
    def lookup():
        try:
            p = parse_body()
            nums = p.get("invoice_numbers")
            if not isinstance(nums,list) or not 1 <= len(nums) <= 1000:
                raise CreditNoteError("INVOICE_NUMBER_LIST_REQUIRED")
            if len(nums) != len(set(nums)):
                raise CreditNoteError("DUPLICATE_SOURCE_INVOICE_NUMBER")
            if any(not isinstance(n,str) or not INVOICE_NUMBER.fullmatch(n) for n in nums):
                raise CreditNoteError("INVALID_SOURCE_INVOICE_NO")
            with connect() as conn:
                rows, prior = invoice_sources(conn,nums)
            out = []
            for num in nums:
                row = rows.get(num)
                if row is None:
                    out.append({"invoice_no":num,
                                "status":"SOURCE_INVOICE_NOT_FOUND_OR_NOT_IMPORTED"})
                else:
                    from decimal import Decimal
                    total = Decimal(row["taxable"])
                    previous = Decimal(str(prior.get(num,"0.00")))
                    remaining = total-previous
                    out.append({
                        "invoice_no":num, "status":"CANCELLED" if row["cancelled"] else row["status"],
                        "invoice_date":row["invoice_date"],
                        "service_month":row["service_month"],
                        "client_name":row["client_name"], "sol_id":row["sol_id"],
                        "gstin":row["gstin"], "original_taxable":str(total),
                        "previously_credited":str(previous),
                        "remaining_taxable":str(remaining),
                        "verified":row["verification_flags"]=="",
                    })
            return jsonify(invoices=out, database_source="ISOLATED_INVOICE_QA",
                           persisted=False, financial_writes=False)
        except CreditNoteError as exc:
            return fail(str(exc),422)
        except Exception:
            return fail("CREDIT_SOURCE_DATABASE_UNAVAILABLE",503)

    @bp.post("/preview")
    def preview():
        try:
            p=parse_body()
            with connect() as conn:
                note=prepared(conn,p)
                check_note_numbers(conn,note["credit_note_no"])
            return jsonify(credit_note=note, persistence="NONE",
                           ledger_posted=False, financial_writes=False)
        except CreditNoteError as exc:
            return fail(str(exc),409 if str(exc)=="DUPLICATE_CREDIT_NOTE_NUMBER" else 422)
        except Exception:
            return fail("CREDIT_NOTE_PREVIEW_DATABASE_UNAVAILABLE",503)

    @bp.post("/finalize")
    def finalize():
        if os.environ.get("SBI_CREDIT_NOTE_FINALIZE_ENABLED") != "1":
            return fail("CREDIT_NOTE_FINALIZE_LOCKED",403)
        if os.environ.get("SBI_INVOICE_GST_DEPLOYMENT_MODE") != "ISOLATED_QA":
            return fail("LIVE_CREDIT_NOTE_REQUIRES_LEDGER_AND_GST_APPROVAL",403)
        actor=getattr(getattr(g,"dil_user",None),"uid",None)
        if not isinstance(actor,str) or not actor:
            return fail("AUTHENTICATED_CREDIT_NOTE_OWNER_REQUIRED",403)
        try:
            p=parse_body()
            req=credit_note_request(p)
            from psycopg.types.json import Jsonb
            from psycopg.errors import UniqueViolation
            with connect() as conn:
                with conn.transaction():
                    db=conn.execute("SELECT current_database() AS db").fetchone()["db"]
                    if db!="invoice_qa":
                        return fail("REFUSE_NON_ISOLATED_QA_DATABASE",403)
                    numbers=sorted(x["invoice_no"] for x in req["entries"])
                    with conn.cursor() as cur:
                        # Prevent concurrent credit notes, cancellations and
                        # invoice finalization from racing per source number.
                        for number in numbers:
                            cur.execute(
                                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                                (number,),
                            )
                        cur.execute(
                            "SELECT pg_advisory_xact_lock(hashtext(%s))",
                            ("CREDIT_NOTE:"+req["credit_note_no"],),
                        )
                    note=prepared(conn,p)
                    check_note_numbers(conn,note["credit_note_no"])
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO sbi_invoice_gst.credit_notes
                               (credit_note_no,credit_note_date,fy,customer_gstin,
                                customer_class,customer_name,state_code,sac_code,
                                reason,taxable,cgst,sgst,total,line_count,created_by_uid)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (note["credit_note_no"], note["credit_note_date"],note["fy"],
                             note["customer_gstin"],note["customer_class"],
                             note["customer_name"], note["state_code"],note["sac_code"],
                             note["reason"],note["taxable"],note["cgst"],note["sgst"],
                             note["total"],note["line_count"],actor),
                        )
                        cur.executemany(
                            """INSERT INTO sbi_invoice_gst.credit_note_lines
                               (credit_note_no,line_no,invoice_no,invoice_date,
                                service_month,branch_key,client_name,sol_id,gstin,
                                sac_code,original_taxable,credited_taxable,invoice_snapshot)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            [(note["credit_note_no"], line["line_no"],line["invoice_no"],
                              line["invoice_date"],line["service_month"],line["branch_key"],
                              line["client_name"],line["sol_id"],line["gstin"],line["sac_code"],
                              line["original_taxable"],line["credited_taxable"],
                              Jsonb(line["invoice_snapshot"]))
                             for line in note["lines"]],
                        )
            return jsonify(
                status="FINALIZED_QA",credit_note_no=note["credit_note_no"],
                line_count=note["line_count"],taxable=note["taxable"],
                cgst=note["cgst"],sgst=note["sgst"],total=note["total"],
                database_recorded=True, ledger_posted=False, gst_filing_updated=False,
                reconciliation_applied=False, financial_execution_enabled=False,
            ),201
        except CreditNoteError as exc:
            return fail(str(exc),409 if str(exc)=="DUPLICATE_CREDIT_NOTE_NUMBER" else 422)
        except UniqueViolation:
            return fail("DUPLICATE_CREDIT_NOTE_NUMBER",409)
        except Exception:
            return fail("CREDIT_NOTE_FINALIZE_DATABASE_UNAVAILABLE",503)

    @bp.get("/pdf")
    def pdf():
        no = request.args.get("no","")
        if not CN_NUMBER.fullmatch(no):
            return fail("INVALID_CREDIT_NOTE_NUMBER",400)
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT credit_note_no,credit_note_date::text AS credit_note_date,
                                  fy,customer_gstin,customer_class,customer_name,
                                  state_code,sac_code,reason,taxable::text AS taxable,
                                  cgst::text AS cgst,sgst::text AS sgst,
                                  total::text AS total,line_count,status
                           FROM sbi_invoice_gst.credit_notes
                           WHERE credit_note_no=%s""", (no,)
                    )
                    note=cur.fetchone()
                    if note is None:
                        return fail("CREDIT_NOTE_NOT_FOUND",404)
                    cur.execute(
                        """SELECT line_no,invoice_no,invoice_date::text AS invoice_date,
                                  service_month,sac_code,credited_taxable::text AS credited_taxable
                           FROM sbi_invoice_gst.credit_note_lines
                           WHERE credit_note_no=%s ORDER BY line_no""",(no,)
                    )
                    lines=cur.fetchall()
                vendor=vendor_profile(conn)
            if not vendor:
                return fail("VENDOR_PROFILE_NOT_VERIFIED",409)
            data=render_credit_note_pdf(note,vendor,lines)
            out=Response(data,content_type="application/pdf")
            out.headers["Content-Disposition"]='attachment; filename="Meghraj-Credit-Note.pdf"'
            out.headers["Cache-Control"]="private, no-store"
            out.headers["X-Content-Type-Options"]="nosniff"
            return out
        except Exception:
            return fail("CREDIT_NOTE_PDF_UNAVAILABLE",503)

    return bp
