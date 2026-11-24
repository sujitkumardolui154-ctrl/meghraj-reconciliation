"""DB-R31.7 genuine Firebase-session smoke INSIDE the private QA container.

No browser/public Caddy route is used. A host-side operator supplies an
already-authorized *test* Firebase account to the secure Identity Toolkit API.
Only its short-lived ID token is streamed via stdin to this ephemeral process.
Neither token nor session cookies are printed or saved. Synthetic data only.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from io import BytesIO, StringIO
import json
import secrets
import sys

from openpyxl import Workbook
from app import app, SITE_ORIGIN

EXPECTED_SOURCE_DB = "sbi_r31_owner_qa_20261125"
TEST_CREDIT = Decimal("118.00")
RAW_SOL = "001505"


def refuse(code):
    print("STOP=DB_R31_" + code, flush=True)
    raise SystemExit(2)


def strict(response, status, code):
    if response.status_code != status:
        refuse(code + "_HTTP_" + str(response.status_code))


def synthetic_excel():
    """Two distinct original source rows; no customer/bank/real invoice data."""
    nonce=secrets.token_hex(8)
    book=Workbook()
    sheet=book.active
    sheet.title="PAYMENT EVIDENCE"
    sheet.append(["Description","SOL ID","Credit Amount"])
    sheet.append(["QA-R31-AUTH-" + nonce, RAW_SOL, "118.00"])
    sheet.append(["QA-R31-INVALID-" + nonce,RAW_SOL,"0"])
    sheet["B2"].number_format="@"
    sheet["B3"].number_format="@"
    stream=BytesIO()
    book.save(stream)
    return BytesIO(stream.getvalue()),"R31-auth-qa-"+nonce+".xlsx"


def reports(client):
    resp=client.get("/api/r31-private-qa/sol-report",base_url=SITE_ORIGIN)
    strict(resp,200,"SOL_REPORT_UNAVAILABLE")
    data=resp.get_json()
    if (data.get("currency")!="INR" or
        data.get("credit_amount_unit")!="RUPEES" or
        data.get("reconciliation_status")!="NOT_CALCULATED" or
        data.get("production_financial_writes") is not False):
        refuse("SOL_REPORT_AMOUNT_UNIT_OR_STATUS")
    groups=data.get("groups")
    if not isinstance(groups,list):
        refuse("SOL_REPORT_GROUP_FORMAT")
    total=Decimal("0")
    for g in groups:
        if g.get("sol_id")==RAW_SOL:
            amt=g.get("credit_received_rupees")
            display=g.get("credit_received_display")
            if not isinstance(amt,str) or display!="₹"+amt:
                refuse("JSON_RUPEE_DISPLAY_INCORRECT")
            if "received_credit_paise" in g:
                refuse("RAW_PAISE_LEAKED_AS_USER_INR")
            total+=Decimal(amt)
    return total


def main():
    contents=sys.stdin.buffer.read(16000)
    if not contents or len(contents)>16000:
        refuse("AUTH_TOKEN_INPUT_SIZE")
    try:
        payload=json.loads(contents)
    except (ValueError,UnicodeError):
        refuse("AUTH_TOKEN_INPUT_FORMAT")
    token=payload.get("id_token") if type(payload) is dict else None
    if type(token) is not str or not (200<=len(token)<=12000):
        refuse("AUTH_ID_TOKEN_INVALID")
    # No logging or storage of the ID token. All work uses Flask's real app
    # and the original Firebase Auth middleware plus same-origin CSRF checks.
    with app.test_client() as client:
        base={"base_url":SITE_ORIGIN}
        csrf_r=client.get("/auth/csrf",**base)
        strict(csrf_r,200,"CSRF_START")
        csrf=csrf_r.get_json().get("csrf_token")
        if type(csrf) is not str or len(csrf)!=64:
            refuse("CSRF_TOKEN_FORMAT")
        headers={"Origin":SITE_ORIGIN,"X-DIL-CSRF":csrf}
        auth=client.post("/auth/session",
            json={"idToken":token},headers=headers,**base)
        if auth.status_code==403:
            refuse("AUTHENTICATED_TEST_ACCOUNT_DASHBOARD_CLAIM_REQUIRED")
        strict(auth,200,"FIREBASE_SIGNIN_SESSION")
        me=client.get("/auth/me",**base)
        strict(me,200,"SESSION_COOKIE_VERIFY")
        print("DB_R31_REAL_FIREBASE_SESSION=PASS",flush=True)

        status=client.get("/api/r31-private-qa/status",**base)
        strict(status,200,"PRIVATE_QA_STATUS")
        state=status.get_json()
        if (state.get("database")!=EXPECTED_SOURCE_DB or
            state.get("production_database_writes") is not False or
            state.get("financial_apply_enabled") is not False):
            refuse("PRIVATE_QA_TARGET_OR_FINANCIAL_LOCK")
        print("DB_R31_AUTHENTICATED_QA_DATABASE_IDENTITY=PASS",flush=True)

        original=reports(client)
        workbook,filename=synthetic_excel()
        uploaded=client.post("/api/payment-evidence/upload",
             data={"file":(workbook,filename)},
             content_type="multipart/form-data",
             headers=headers,**base)
        strict(uploaded,201,"ORIGINAL_PRIVATE_EXCEL_UPLOAD")
        receipt=uploaded.get_json() or {}
        rid=receipt.get("receipt_id")
        if (type(rid) is not str or len(rid)!=32 or
            receipt.get("source_rows")!=2 or
            receipt.get("valid_rows")!=1 or
            receipt.get("review_rows")!=1 or
            receipt.get("valid_credit_total")!="118.00"):
            refuse("ORIGINAL_UPLOAD_RECEIPT_EVIDENCE_INCORRECT")
        print("DB_R31_REAL_FIREBASE_EXCEL_RECEIPT=PASS",flush=True)

        bad=client.post(
            "/api/r31-private-qa/receipts/"+rid+"/sync",
            headers={"Origin":"https://example.invalid",
                     "X-DIL-CSRF":csrf},**base)
        strict(bad,403,"CROSS_ORIGIN_CSRF_REJECTION")
        print("DB_R31_REAL_FIREBASE_CSRF_CROSS_ORIGIN_REJECTED=PASS",flush=True)

        sync_url="/api/r31-private-qa/receipts/"+rid+"/sync"
        first=client.post(sync_url,headers=headers,**base)
        strict(first,201,"QA_PG_RECEIPT_SYNC")
        if (first.get_json() or {}).get("status")!="SOURCE_COMMITTED_NOT_RECONCILED":
            refuse("PG_SOURCE_ONLY_RECEIPT_STATE")
        print("DB_R31_REAL_FIREBASE_QA_PG_SOURCE_SYNC=PASS",flush=True)

        detail=client.get("/api/r31-private-qa/payment-details",**base)
        strict(detail,200,"OWNER_RECEIPT_DETAILS")
        saved=[r for r in (detail.get_json().get("rows") or [])
               if r.get("source_receipt_id")==rid]
        if len(saved)!=2:
            refuse("SOURCE_RECEIPT_ROW_COUNT")
        good=[r for r in saved if r.get("credit_amount_rupees")=="118.00"]
        invalid=[r for r in saved
            if r.get("source_status")=="EXCLUDED_INVALID_SOURCE"]
        if (len(good)!=1 or len(invalid)!=1 or
            invalid[0].get("credit_amount_rupees") is not None or
            any(r.get("sol_id")!=RAW_SOL for r in saved) or
            any(r.get("reconciliation_status")!="NOT_CALCULATED" for r in saved)):
            refuse("SOURCE_DETAILS_OR_MONEY_INCORRECT")
        print("DB_R31_ORIGINAL_SOL_INVALID_ROW_AND_INR_DETAILS=PASS",flush=True)

        after=reports(client)
        if after-original!=TEST_CREDIT:
            refuse("SOL_INR_REPORT_CREDIT_DELTA_NOT_118_00")
        report=client.get("/api/r31-private-qa/sol-report.csv",**base)
        strict(report,200,"SOL_INR_CSV")
        decoded=report.data.decode("utf-8-sig")
        rows=list(csv.DictReader(StringIO(decoded)))
        values=[Decimal(r["Credit Received (INR)"]) for r in rows
                if r.get("SOL ID")==RAW_SOL]
        if sum(values,Decimal("0"))!=after:
            refuse("SOL_CSV_JSON_RUPEE_PARITY")
        print("DB_R31_REAL_FIREBASE_INR_118_00_REPORT_PARITY=PASS",flush=True)

        repeat=client.post(sync_url,headers=headers,**base)
        strict(repeat,200,"RECEIPT_REPLAY")
        if (repeat.get_json() or {}).get("status")!="ALREADY_RECORDED" or
            reports(client)!=after:
            refuse("REPLAY_DUPLICATED_PAYMENT_CREDIT")
        print("DB_R31_AUTHENTICATED_REPLAY_NO_DOUBLE_CREDIT=PASS",flush=True)
    print("DB_R31_REAL_FIREBASE_CREDENTIALS_SAVED=NO",flush=True)
    print("DB_R31_PRODUCTION_FINANCIAL_WRITES=NONE_BY_QA",flush=True)
    print("DB_R31_RELEASE_STATUS=PRIVATE_REAL_FIREBASE_QA_PASS_NOT_PUBLIC",flush=True)


if __name__=="__main__":
    main()
