"""R29 isolated authenticated AWS *pre-screened* candidate review gateway.

This gateway does not parse the original XLSX, execute full Master v2.51 /
Matrix v2.39, allocate real bank credit, assign PAYMENT!M or access a database.
It accepts already-screened row/edge assessments as a disposable preview.
Never route production financial requests here; do not attach this to the
existing AWS reporting gateway or public preview.
"""
from __future__ import annotations
import hmac
import os
import re
from flask import Flask, jsonify, request
from sbi_r28_owner_deployment_and_row_exclusion_policy import (
    ScreenedSourceRecord, ScreenedMatch, DeploymentScopeRefusal,
    partition_screened_source, DEPLOYMENT_SCOPE,
)

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=512*1024
MAX_RECORDS=1000
MAX_MATCHES=4000
STAGE="R29_AWS_CALCULATION_PRESCREEN_PREVIEW_ISOLATED"
MODE="PRE_SCREENED_CANDIDATE_REVIEW_ONLY"
ENGINE="FULL_V251_V239_NOT_CONNECTED"
SHA=re.compile(r"[0-9a-f]{64}\Z")
KEYS=frozenset(("source_sha256","mode","records","matches"))
ROW_KEYS=frozenset(("role","source_row","source_identity","result","reasons"))
EDGE_KEYS=frozenset(("invoice_row","payment_row","result","reasons"))


class ContractRefusal(ValueError):
    pass


def require(ok,code):
    if not ok:
        raise ContractRefusal(code)


def error(code,status):
    return jsonify({
        "stage":STAGE,"status":"REVIEW_ONLY",
        "reason_code":code,"financial_apply":"LOCKED",
        "reconciliation_executed":False,
        "real_bank_allocations":0,
        "real_database_writes":0,
    }),status


def enabled():
    return (os.environ.get("SBI_CALC_PREVIEW_ENABLED")=="true"
            and os.environ.get("SBI_FINANCIAL_APPLY")=="LOCKED")


def authorized():
    username=os.environ.get("SBI_CALC_PREVIEW_USERNAME","")
    password=os.environ.get("SBI_CALC_PREVIEW_PASSWORD","")
    if not username or len(password)<24:
        return error("PREVIEW_AUTH_NOT_CONFIGURED",503)
    auth=request.authorization
    if (auth is None
            or str(auth.type).casefold()!="basic"
            or not hmac.compare_digest(str(auth.username or ""),username)
            or not hmac.compare_digest(str(auth.password or ""),password)):
        response,status=error("AUTH_REQUIRED",401)
        response.headers["WWW-Authenticate"]='Basic realm="SBI isolated calculation preview"'
        return response,status
    return None


def tuple_reasons(raw):
    require(type(raw) is list and len(raw)<=10 and
            all(type(x) is str for x in raw),"INVALID_REASON_LIST")
    return tuple(raw)


def parse_body(payload):
    require(type(payload) is dict and set(payload)==KEYS,"INVALID_REQUEST_SCHEMA")
    require(payload["mode"]==MODE,"UNAPPROVED_CALCULATION_MODE")
    require(type(payload["source_sha256"]) is str and
            SHA.fullmatch(payload["source_sha256"]),"ORIGINAL_SOURCE_SHA256_REQUIRED")
    rows=payload["records"];edges=payload["matches"]
    require(type(rows) is list and len(rows)<=MAX_RECORDS,
            "SOURCE_PREVIEW_SIZE_LIMIT")
    require(type(edges) is list and len(edges)<=MAX_MATCHES,
            "EDGE_PREVIEW_SIZE_LIMIT")
    checked=[]
    for r in rows:
        require(type(r) is dict and set(r)==ROW_KEYS,"INVALID_RECORD_SCHEMA")
        require(type(r["source_row"]) is int,"INVALID_SOURCE_ROW_TYPE")
        checked.append(ScreenedSourceRecord(
            r["role"],r["source_row"],r["source_identity"],r["result"],
            tuple_reasons(r["reasons"])))
    matching=[]
    for e in edges:
        require(type(e) is dict and set(e)==EDGE_KEYS,"INVALID_EDGE_SCHEMA")
        require(type(e["invoice_row"]) is int and type(e["payment_row"]) is int,
                "INVALID_MATCH_ROW_TYPE")
        matching.append(ScreenedMatch(e["invoice_row"],e["payment_row"],
                                   e["result"],tuple_reasons(e["reasons"])))
    return tuple(checked),tuple(matching)


@app.after_request
def secure(response):
    response.headers["Cache-Control"]="no-store, private"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["Content-Security-Policy"]="default-src 'none'"
    return response


@app.before_request
def deny():
    # Isolated app. Intentionally no generic /reports, /upload, /apply, SQL
    # or reconciliation-status endpoints.
    if (request.path,request.method) not in (
            ("/healthz","GET"),("/readyz","GET"),
            ("/api/candidate-screen","POST")):
        return error("ROUTE_OR_METHOD_DISABLED",403)


@app.get("/healthz")
def health():
    return jsonify({
        "stage":STAGE,"service":"sbi-private-calculation-prescreen",
        "mode":MODE,"engine":ENGINE,
        "financial_apply":"LOCKED","real_database_writes":0,
        "full_v251_v239_engine_connected":False,
        "formal_financial_certificate_required":False,
        "staging_deployment_verified":False,
    })


@app.get("/readyz")
def ready():
    if not enabled():
        return error("PREVIEW_DISABLED_OR_FINANCIAL_APPLY_UNSAFE",503)
    if (not os.environ.get("SBI_CALC_PREVIEW_USERNAME")
            or len(os.environ.get("SBI_CALC_PREVIEW_PASSWORD",""))<24):
        return error("PREVIEW_AUTH_NOT_CONFIGURED",503)
    return jsonify({
        "stage":STAGE,"status":"READY_FOR_PRE_SCREENED_TEST_ONLY",
        "engine":ENGINE,
        "full_v251_v239_engine_connected":False,
        "payment_final_status_authorized":False,
        "financial_apply":"LOCKED",
    })


@app.post("/api/candidate-screen")
def candidate_screen():
    if not enabled():
        return error("PREVIEW_DISABLED_OR_FINANCIAL_APPLY_UNSAFE",503)
    denied=authorized()
    if denied is not None:
        return denied
    if request.content_type!="application/json":
        return error("JSON_CONTENT_TYPE_REQUIRED",415)
    try:
        payload=request.get_json(silent=True)
        rows,edges=parse_body(payload)
        res=partition_screened_source(
            rows,edges,source_sha256=payload["source_sha256"],
            financial_apply="LOCKED")
    except (ContractRefusal,DeploymentScopeRefusal) as e:
        return error(str(e),422)
    except Exception:
        # No request values or customer names ever appear in responses/logs.
        return error("INVALID_CANDIDATE_SCREEN_REQUEST",422)
    # Do not return source identity/client/amount or source workbook contents.
    return jsonify({
        "stage":STAGE,
        "mode":MODE,
        "engine":ENGINE,
        "scope":DEPLOYMENT_SCOPE,
        "source_sha256":res["source_sha256"],
        "summary":res["summary"],
        "eligible_source_rows":[{"role":role,"row":row}
                 for role,row,_ in res["eligible_records"]],
        "excluded_source_rows":[{"role":r["role"],"row":r["source_row"],
                   "reasons":r["reason_codes"]} for r in res["excluded_records"]],
        "held_source_rows":[{"role":r["role"],"row":r["source_row"],
                   "reasons":r["reason_codes"]} for r in res["held_records"]],
        "candidate_row_pairs":res["method_candidates"],
        "excluded_row_pairs":res["excluded_pairs"],
        "held_row_pairs":res["held_pairs"],
        "screening_evidence_independently_verified":False,
        "full_matching_rules_executed":False,
        "formal_financial_certificate_required":False,
        "source_workbook_modified":False,
        "final_payment_status_assigned":False,
        "reconciliation_executed":False,
        "real_bank_allocations":0,
        "real_database_writes":0,
        "financial_apply":"LOCKED",
    })


if __name__=="__main__":
    raise SystemExit("Start using restricted, non-root gunicorn, behind private TLS ingress")
