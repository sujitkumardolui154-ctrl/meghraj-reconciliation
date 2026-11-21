"""NEW engine 21 11 2026 — Stage 4 new-only signed-intake / durable proposal ledger.

ENGINEERING PREVIEW ONLY. There are NO Flask routes, Firebase credentials, bank API,
paid/OK status updates, historical-source imports or financial posting functions.

An HMAC proves only that a preconfigured *internal evidence gateway* signed the
canonical JSON. It does NOT independently establish that SBI originated a credit.
Production must bind the gateway to an independently verified bank source and
an authenticated staff principal before any real input can be accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import hmac
import json
import os
import re
import sqlite3

HEX64 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SOL = re.compile(r"[0-9]{1,12}\Z", re.ASCII)
REF = re.compile(r"[A-Z0-9][A-Z0-9/_-]{3,79}\Z", re.ASCII)
INVOICE = re.compile(r"[A-Z0-9][A-Z0-9/_-]{3,79}\Z", re.ASCII)
MONEY = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?\Z", re.ASCII)
KEYS_BANK = frozenset({
    "schema", "issuer", "source_kind", "source_sha256", "source_row", "source_column",
    "statement_sha256", "bank_date", "payment_reference", "sol_id", "client_name",
    "upload_row_sha256",
    "description", "credit_amount", "invoice_reference", "service_month",
})
KEYS_INVOICE = frozenset({
    "schema", "issuer", "source_kind", "source_sha256", "source_row",
    "invoice_no", "invoice_date", "sol_id", "client_name", "service_month",
    "taxable", "cgst", "sgst", "gross", "paid_marker", "credit_note",
})
ALLOWED_ROLES = {"INTAKE", "REVIEWER", "CANDIDATE_ENGINE"}

class Stage4Blocked(ValueError):
    pass

def fail(message: str) -> None:
    raise Stage4Blocked(message)

def strict_iso(value: object) -> date:
    if type(value) is not str or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        fail("ISO_DATE_REQUIRED")
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail("INVALID_DATE")

def paise(value: object, *, nonzero: bool = True) -> int:
    if type(value) is not str or not MONEY.fullmatch(value):
        fail("STRICT_DECIMAL_STRING_REQUIRED")
    try:
        v = Decimal(value)
        cents = v * 100
    except InvalidOperation:
        fail("INVALID_AMOUNT")
    if cents != cents.to_integral_value() or v < 0 or (nonzero and not v > 0):
        fail("POSITIVE_EXACT_AMOUNT_REQUIRED")
    return int(cents)

def sha(value: object) -> str:
    if type(value) is not str or not HEX64.fullmatch(value):
        fail("SHA256_HEX_REQUIRED")
    return value

def canon(payload: object) -> bytes:
    if type(payload) is not dict:
        fail("EXACT_SIGNED_MAPPING_REQUIRED")
    # Reject float & non-JSON types and avoid ambiguous canonicalization.
    for val in payload.values():
        if type(val) not in (str, bool, int):
            fail("UNSAFE_SIGNED_VALUE_TYPE")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()

@dataclass(frozen=True)
class Stage4Policy:
    issuer: str
    activation_date: str
    as_of_date: str
    secret: bytes
    source_kind: str = "NEW_ONLY"
    finance_apply_enabled: bool = False

    def __post_init__(self) -> None:
        if self.finance_apply_enabled is not False:
            fail("PRODUCTION_FINANCE_APPLY_FORBIDDEN")
        if (type(self.issuer) is not str or not re.fullmatch(r"[A-Z0-9_]{8,48}", self.issuer)):
            fail("ISSUER_PIN_REQUIRED")
        if type(self.secret) is not bytes or len(self.secret) < 32:
            fail("SERVER_OWNED_HMAC_SECRET_REQUIRED")
        if self.source_kind != "NEW_ONLY":
            fail("NEW_ONLY_SCOPE_REQUIRED")
        if strict_iso(self.as_of_date) < strict_iso(self.activation_date):
            fail("CUTOFF_AFTER_SERVER_DATE")

@dataclass(frozen=True)
class Principal:
    """Must be constructed by a trusted authentication adapter, NOT an HTTP body."""
    uid: str
    role: str

    def __post_init__(self) -> None:
        if (type(self.uid) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{4,64}",self.uid)
                or self.role not in ALLOWED_ROLES):
            fail("PRINCIPAL_FORMAT_INVALID")

def check_actor(actor: object, role: str) -> Principal:
    if type(actor) is not Principal or actor.role != role:
        fail("TRUSTED_PRINCIPAL_ROLE_REQUIRED")
    return actor

def verify_attestation(body: object, tag: object, policy: Stage4Policy, kind: str) -> tuple[dict,str]:
    if type(body) is not dict or set(body) != (KEYS_BANK if kind == "bank" else KEYS_INVOICE):
        fail("ATTESTATION_SCHEMA_MISMATCH")
    raw=canon(body)
    if type(tag) is not str or not HEX64.fullmatch(tag):
        fail("ATTESTATION_TAG_REQUIRED")
    expected=hmac.new(policy.secret, b"SBI_STG4_V1:"+kind.encode()+b":"+raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, tag):
        fail("ATTESTATION_SIGNATURE_MISMATCH")
    if body["issuer"] != policy.issuer or body["source_kind"] != policy.source_kind:
        fail("ISSUER_OR_NEW_ONLY_SOURCE_MISMATCH")
    if (body["schema"] != ("SBI_BANK_EVIDENCE_V1" if kind=="bank" else "SBI_INVOICE_EVIDENCE_V1")):
        fail("EVIDENCE_SCHEMA_VERSION_REQUIRED")
    sha(body["source_sha256"])
    if type(body["source_row"]) is not int or body["source_row"] < 2:
        fail("SOURCE_ROW_REQUIRED")
    return body, hashlib.sha256(raw).hexdigest()

def _identity(body: dict) -> None:
    if (type(body["sol_id"]) is not str or not SOL.fullmatch(body["sol_id"])
            or type(body["client_name"]) is not str or not body["client_name"].strip()
            or len(body["client_name"])>160 or body["client_name"]!=body["client_name"].strip()):
        fail("SOL_CLIENT_IDENTITY_INVALID")

UPLOAD_HEADERS = frozenset({"Description", "SOL ID", "Credit Amount"})

def upload_row_sha256(row: object) -> str:
    """Digest the unmodified existing three-column evidence row, not a bank proof."""
    if type(row) is not dict or set(row) != UPLOAD_HEADERS:
        fail("EXACT_THREE_COLUMN_UPLOAD_REQUIRED")
    if (type(row["Description"]) is not str or not row["Description"].strip()
            or len(row["Description"]) > 1024 or
            type(row["SOL ID"]) is not str or not SOL.fullmatch(row["SOL ID"])):
        fail("UPLOAD_DESCRIPTION_OR_SOL_INVALID")
    paise(row["Credit Amount"])
    raw=json.dumps({"schema":"SBI_UPLOAD_ROW_V1","values":row},
                   sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()

def bank_fields(body: dict, policy: Stage4Policy) -> dict:
    _identity(body)
    for key in ("payment_reference", "invoice_reference"):
        if type(body[key]) is not str or not REF.fullmatch(body[key]):
            fail("EXACT_REFERENCE_REQUIRED")
    if body["source_column"]!="PAYMNENT!I":
        fail("BANK_CREDIT_MUST_BE_COLUMN_I")
    sha(body["statement_sha256"])
    sha(body["upload_row_sha256"])
    if type(body["description"]) is not str or not (0 < len(body["description"].strip())<=1024):
        fail("NARRATION_REQUIRED")
    d=strict_iso(body["bank_date"])
    if not strict_iso(policy.activation_date)<=d<=strict_iso(policy.as_of_date):
        fail("BANK_DATE_OUTSIDE_NEW_ONLY_BOUNDARY")
    if type(body["service_month"]) is not str or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])",body["service_month"]):
        fail("SERVICE_MONTH_INVALID")
    return {"credit_paise": paise(body["credit_amount"])}

def invoice_fields(body: dict, policy: Stage4Policy) -> dict:
    _identity(body)
    if type(body["invoice_no"]) is not str or not INVOICE.fullmatch(body["invoice_no"]):
        fail("INVOICE_NUMBER_REQUIRED")
    d=strict_iso(body["invoice_date"])
    if not strict_iso(policy.activation_date)<=d<=strict_iso(policy.as_of_date):
        fail("INVOICE_DATE_OUTSIDE_NEW_ONLY_BOUNDARY")
    if type(body["service_month"]) is not str or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])",body["service_month"]):
        fail("SERVICE_MONTH_INVALID")
    if body["paid_marker"] != "" or body["credit_note"] is not False:
        fail("PAID_OR_CREDIT_NOTE_SOURCE_HELD")
    total=sum(paise(body[x],nonzero=(x=="taxable")) for x in ("taxable","cgst","sgst"))
    gross=paise(body["gross"])
    if gross!=total:
        fail("INVOICE_GROSS_MISMATCH")
    return {"gross_paise":gross}

class NewOnlyCandidateLedger:
    """Durable *proposal* store; NOT financial settlement ledger.

    Caller must provide a dedicated database path in an isolated staging
    location. No production credentials, DB URLs, bank clients or source
    workbook paths accepted. No financial Apply method exists.
    """
    def __init__(self, path: str, policy: Stage4Policy):
        if type(path) is not str or path == ":memory:" or not path.endswith(".sqlite3"):
            fail("EXPLICIT_ISOLATED_SQLITE_FILE_REQUIRED")
        if not Path(path).parent.is_dir() or Path(path).is_symlink():
            fail("DEDICATED_DATABASE_DIRECTORY_REQUIRED")
        if not isinstance(policy, Stage4Policy):
            fail("SERVER_POLICY_REQUIRED")
        self._policy=policy
        self._db=sqlite3.connect(path,timeout=5,isolation_level=None)
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS receipts(
          ref TEXT PRIMARY KEY, evidence_sha TEXT NOT NULL UNIQUE,
          source_sha TEXT NOT NULL, row_id INTEGER NOT NULL,
          bank_date TEXT NOT NULL, statement_sha TEXT NOT NULL,
          invoice_ref TEXT NOT NULL, sol TEXT NOT NULL, client TEXT NOT NULL,
          service_month TEXT NOT NULL, credit_paise INTEGER NOT NULL CHECK(credit_paise>0),
          approved_by TEXT, uploaded_by TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN('PENDING_REVIEW','REVIEWED')));
        CREATE TABLE IF NOT EXISTS invoices(
          invoice_no TEXT PRIMARY KEY, evidence_sha TEXT NOT NULL UNIQUE,
          source_sha TEXT NOT NULL, invoice_date TEXT NOT NULL,
          sol TEXT NOT NULL, client TEXT NOT NULL, service_month TEXT NOT NULL,
          gross_paise INTEGER NOT NULL CHECK(gross_paise>0), uploaded_by TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reservations(
          ref TEXT NOT NULL, invoice_no TEXT NOT NULL,
          paise INTEGER NOT NULL CHECK(paise>0), review_sha TEXT NOT NULL,
          PRIMARY KEY(ref, invoice_no),
          FOREIGN KEY(ref) REFERENCES receipts(ref),
          FOREIGN KEY(invoice_no) REFERENCES invoices(invoice_no));
        CREATE TABLE IF NOT EXISTS audit(
          event_id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
          subject_digest TEXT NOT NULL, actor TEXT NOT NULL);
        """)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "NewOnlyCandidateLedger":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _txn(self, op):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            result=op()
            self._db.execute("COMMIT")
            return result
        except Exception:
            if self._db.in_transaction:self._db.execute("ROLLBACK")
            raise

    def stage_uploaded_bank(self, row: dict, body: dict, tag: str, *, actor: Principal) -> dict:
        """Existing three-column row bound to signed new-only bank metadata.

        The HMAC authenticates the internal issuer only; a separate bank-source
        verifier and Firebase role mapping are required before production.
        """
        check_actor(actor,"INTAKE")
        signed, _digest=verify_attestation(body,tag,self._policy,"bank")
        rowhash=upload_row_sha256(row)
        if rowhash!=signed["upload_row_sha256"]:
            fail("SIGNED_UPLOAD_ROW_DIGEST_MISMATCH")
        if (row["Description"] != signed["description"] or
            row["SOL ID"] != signed["sol_id"] or
            paise(row["Credit Amount"]) != paise(signed["credit_amount"])):
            fail("SIGNED_BANK_CREDIT_SOURCE_CONFLICT")
        return self.record_bank(signed,tag,actor=actor)

    def record_bank(self, body: dict, tag: str, *, actor: Principal) -> dict:
        check_actor(actor,"INTAKE")
        verified,digest=verify_attestation(body,tag,self._policy,"bank")
        info=bank_fields(verified,self._policy)
        def run():
            old=self._db.execute("SELECT evidence_sha FROM receipts WHERE ref=?",(body["payment_reference"],)).fetchone()
            if old:
                if old[0]==digest:return {"status":"SAME_SIGNED_RECEIPT_ALREADY_STAGED","idempotent":True,"financial_writes":False}
                fail("DUPLICATE_UTR_WITH_CONFLICTING_EVIDENCE")
            self._db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                body["payment_reference"], digest,body["source_sha256"],body["source_row"],
                body["bank_date"],body["statement_sha256"],body["invoice_reference"],
                body["sol_id"],body["client_name"],body["service_month"], info["credit_paise"],
                None,actor.uid,"PENDING_REVIEW"))
            self._db.execute("INSERT INTO audit(action,subject_digest,actor) VALUES(?,?,?)",("STAGE_BANK",digest,actor.uid))
            return {"status":"PENDING_REVIEW","idempotent":False,"financial_writes":False}
        try:return self._txn(run)
        except sqlite3.IntegrityError:fail("DUPLICATE_EVIDENCE_OR_UTR")

    def record_invoice(self, body: dict, tag: str, *, actor: Principal) -> dict:
        check_actor(actor,"INTAKE")
        verified,digest=verify_attestation(body,tag,self._policy,"invoice")
        info=invoice_fields(verified,self._policy)
        def run():
            old=self._db.execute("SELECT evidence_sha FROM invoices WHERE invoice_no=?",(body["invoice_no"],)).fetchone()
            if old:
                if old[0]==digest:return {"status":"SAME_SIGNED_INVOICE_ALREADY_STAGED","idempotent":True,"financial_writes":False}
                fail("DUPLICATE_INVOICE_WITH_CONFLICTING_EVIDENCE")
            self._db.execute("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?)",(
                body["invoice_no"],digest,body["source_sha256"],body["invoice_date"],
                body["sol_id"],body["client_name"],body["service_month"],info["gross_paise"],actor.uid))
            self._db.execute("INSERT INTO audit(action,subject_digest,actor) VALUES(?,?,?)",("STAGE_INVOICE",digest,actor.uid))
            return {"status":"NEW_ONLY_INVOICE_STAGED","idempotent":False,"financial_writes":False}
        try:return self._txn(run)
        except sqlite3.IntegrityError:fail("DUPLICATE_INVOICE_EVIDENCE")

    def review_bank(self, ref: str, *, actor: Principal) -> dict:
        check_actor(actor,"REVIEWER")
        def run():
            r=self._db.execute("SELECT uploaded_by, approved_by, state, evidence_sha FROM receipts WHERE ref=?",(ref,)).fetchone()
            if r is None:fail("RECEIPT_NOT_FOUND")
            if r[0]==actor.uid:fail("SELF_REVIEW_DENIED")
            if r[2]=="REVIEWED":return {"status":"ALREADY_REVIEWED","financial_writes":False}
            self._db.execute("UPDATE receipts SET approved_by=?,state='REVIEWED' WHERE ref=? AND state='PENDING_REVIEW'",(actor.uid,ref))
            self._db.execute("INSERT INTO audit(action,subject_digest,actor) VALUES(?,?,?)",("REVIEW_BANK",r[3],actor.uid))
            return {"status":"REVIEWED_FOR_CANDIDATE_ONLY","financial_writes":False}
        return self._txn(run)

    def reserve_candidate(self, ref: str, invoice_no: str, amount_text: str, *,
                          engine_review_sha: str, actor: Principal) -> dict:
        """Conserves capacity only. Never sets invoice paid/OK/settled state."""
        check_actor(actor,"CANDIDATE_ENGINE")
        sha(engine_review_sha)
        cents=paise(amount_text)
        def run():
            b=self._db.execute("SELECT invoice_ref,sol,client,service_month,credit_paise,bank_date,state FROM receipts WHERE ref=?",(ref,)).fetchone()
            i=self._db.execute("SELECT sol,client,service_month,gross_paise,invoice_date FROM invoices WHERE invoice_no=?",(invoice_no,)).fetchone()
            if b is None or i is None:fail("SOURCE_NOT_REGISTERED")
            if b[6]!="REVIEWED":fail("RECEIPT_DUAL_REVIEW_REQUIRED")
            if b[0]!=invoice_no:fail("EXACT_INVOICE_REFERENCE_REQUIRED")
            if b[1]!=i[0] or b[2]!=i[1] or b[3]!=i[2]:fail("SOL_CLIENT_PERIOD_CONFLICT")
            days=(strict_iso(b[5])-strict_iso(i[4])).days
            if not 0<=days<=180:fail("DATE_CHRONOLOGY_OR_180D_CONFLICT")
            prior=self._db.execute("SELECT paise,review_sha FROM reservations WHERE ref=? AND invoice_no=?",(ref,invoice_no)).fetchone()
            if prior:
                if prior==(cents,engine_review_sha):return {"status":"SAME_PROPOSAL_ALREADY_RESERVED","idempotent":True,"financial_writes":False}
                fail("CONFLICTING_REPEAT_RESERVATION")
            pay_total=self._db.execute("SELECT COALESCE(SUM(paise),0) FROM reservations WHERE ref=?",(ref,)).fetchone()[0]
            inv_total=self._db.execute("SELECT COALESCE(SUM(paise),0) FROM reservations WHERE invoice_no=?",(invoice_no,)).fetchone()[0]
            if pay_total+cents>b[4]:fail("PAYMENT_CREDIT_OVER_RESERVED")
            if inv_total+cents>i[3]:fail("INVOICE_CAPACITY_OVER_RESERVED")
            self._db.execute("INSERT INTO reservations(ref,invoice_no,paise,review_sha) VALUES(?,?,?,?)",(ref,invoice_no,cents,engine_review_sha))
            self._db.execute("INSERT INTO audit(action,subject_digest,actor) VALUES(?,?,?)",("RESERVE_CANDIDATE",engine_review_sha,actor.uid))
            return {"status":"CANDIDATE_RESERVED_NOT_SETTLED","idempotent":False,"financial_writes":False}
        return self._txn(run)

    def status(self) -> dict:
        counts={name:self._db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in ("receipts","invoices","reservations","audit")}
        return {"engine":"NEW engine 21 11 2026", "mode":"NEW_ONLY_OFFLINE_INTEGRATION_PREVIEW",
                "counts":counts,"persistent_candidate_ledger":True,
                "bank_source_authenticated":False,"firebase_authenticated":False,
                "invoice_paid_markers_updated":False,"financial_writes":False,
                "financial_apply_enabled":False,"production_approved":False,
                "historical_records_processed":False}