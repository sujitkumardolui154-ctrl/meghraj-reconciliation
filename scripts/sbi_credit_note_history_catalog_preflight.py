#!/usr/bin/env python3
"""READ-ONLY PostgreSQL historical invoice source CATALOG discovery.

Operator may run this script on the dedicated historical reporting role.
It NEVER reads invoice values, performs DDL, copies data, or alters ledgers.
A matching relation name/column list alone DOES NOT approve credit note issue.
Credentials and DSNs are neither printed nor stored in the JSON result.
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone

MAIN_DATABASES = frozenset(("sbi_reconciliation_main", "sbi_reconciliation_staging"))
CANONICAL_FIELDS = frozenset((
    "invoice_no", "invoice_date", "service_month", "client_name",
    "sol_id", "gstin", "taxable", "cgst", "sgst", "total",
))
ATTESTED_FIELDS = frozenset((
    "verification_status", "source_snapshot_sha256",
    "historical_credit_coverage_status", "gst_filing_status",
    "payment_reconciliation_status",
))


class HistorySourceProbeError(RuntimeError):
    pass


def candidate_review(columns, *, write_granted):
    fields = {x.lower() for x in columns}
    return {
        "canonical_fields_present": sorted(CANONICAL_FIELDS & fields),
        "canonical_fields_missing": sorted(CANONICAL_FIELDS - fields),
        "attested_fields_present": sorted(ATTESTED_FIELDS & fields),
        "attested_fields_missing": sorted(ATTESTED_FIELDS - fields),
        "role_can_modify_relation": bool(write_granted),
        # Source identity, duplicate, financial and tax attestation must
        # follow BEFORE allowing any issued credit note against history.
        "source_approved_for_credit_note_issue": False,
    }


def inspect_catalog(conn, *, allow_isolated_qa=False):
    """Inspect metadata in a transaction already forced READ ONLY."""
    meta = conn.execute(
        """SELECT current_database() AS db, current_user AS role,
                  current_setting('transaction_read_only') AS readonly"""
    ).fetchone()
    name = meta["db"]
    if name not in MAIN_DATABASES and not (
        allow_isolated_qa and name == "invoice_qa"
    ):
        raise HistorySourceProbeError("UNAPPROVED_HISTORY_DATABASE")
    if meta["readonly"] not in ("on", "true"):
        raise HistorySourceProbeError("POSTGRES_TRANSACTION_NOT_READ_ONLY")
    sql = """
        SELECT c.table_schema, c.table_name, c.column_name, c.ordinal_position,
               has_table_privilege(
                 format('%I.%I', c.table_schema, c.table_name),
                 'SELECT'
               ) AS can_select,
               (
                 has_table_privilege(
                   format('%I.%I', c.table_schema, c.table_name), 'INSERT'
                 ) OR
                 has_table_privilege(
                   format('%I.%I', c.table_schema, c.table_name), 'UPDATE'
                 ) OR
                 has_table_privilege(
                   format('%I.%I', c.table_schema, c.table_name), 'DELETE'
                 )
               ) AS can_write
          FROM information_schema.columns c
          JOIN information_schema.tables t
            ON t.table_schema=c.table_schema
           AND t.table_name=c.table_name
         WHERE c.table_schema NOT IN ('pg_catalog','information_schema')
           AND (c.table_name ILIKE '%invoice%'
                OR c.table_name ILIKE '%credit%')
         ORDER BY c.table_schema, c.table_name, c.ordinal_position
         LIMIT 5000
    """
    rows = conn.execute(sql).fetchall()
    names = {}
    for row in rows:
        key = (row["table_schema"], row["table_name"])
        item = names.setdefault(key, {
            "schema": row["table_schema"], "relation": row["table_name"],
            "columns": [], "can_select": False, "can_write": False
        })
        item["columns"].append(row["column_name"])
        item["can_select"] = item["can_select"] or bool(row["can_select"])
        item["can_write"] = item["can_write"] or bool(row["can_write"])
    candidates = []
    for key in sorted(names):
        item = names[key]
        review = candidate_review(item["columns"], write_granted=item["can_write"])
        candidates.append({
            "schema": item["schema"], "relation": item["relation"],
            "can_select": item["can_select"],
            "column_count": len(item["columns"]), **review
        })
    fingerprint_input = [{
        "schema": key[0], "relation": key[1], "columns": names[key]["columns"]
    } for key in sorted(names)]
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input,sort_keys=True,
                   separators=(",",":")).encode("utf-8")
    ).hexdigest()
    return {
        "probe": "SBI_CREDIT_NOTE_HISTORY_CATALOG_V1",
        "database": name, "role": meta["role"],
        "read_only_transaction": True,
        "query_scope": "SCHEMA_METADATA_ONLY_NO_FINANCIAL_ROWS",
        "catalog_truncated": len(rows) >= 5000,
        "catalog_sha256": fingerprint,
        "candidate_count": len(candidates),
        "candidate_invoice_relations": candidates,
        "authoritative_invoice_relation_verified": False,
        "credit_note_history_issuance_allowed": False,
        "requires": [
            "OWNER_APPROVED_AUTHORITATIVE_RELATION_AND_COLUMN_MAPPING",
            "INDEPENDENT_DUPLICATE_AND_SOURCE_INTEGRITY_REVIEW",
            "HISTORICAL_CREDIT_NOTE_REGISTER_COVERAGE",
            "BANK_RECONCILIATION_AND_GST_FILING_CROSSCHECK",
            "VERIFIED_READ_ONLY_ROLE_AND_REAL_FIREBASE_OWNER_QA",
        ],
        "financial_writes": False,
    }


def run_schema_probe(dsn, *, allow_isolated_qa=False):
    if not isinstance(dsn, str) or not dsn:
        raise HistorySourceProbeError("READ_ONLY_DATABASE_DSN_REQUIRED")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(
        dsn, row_factory=dict_row, autocommit=True, connect_timeout=6,
        options="-c default_transaction_read_only=on -c statement_timeout=12000",
    ) as conn:
        conn.execute("BEGIN TRANSACTION READ ONLY")
        try:
            result = inspect_catalog(conn,allow_isolated_qa=allow_isolated_qa)
        finally:
            conn.execute("ROLLBACK")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="SBI_HISTORY_REPORT_READONLY_DSN",
                        help="Environment variable name holding the private DSN")
    parser.add_argument("--isolated-qa", action="store_true",
                        help="Permit database invoice_qa for synthetic CI only")
    parser.add_argument("--output",
                        help="Write JSON to the chosen local private path")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", args.dsn_env):
        parser.error("Invalid env var name")
    try:
        report = run_schema_probe(
            os.environ.get(args.dsn_env),
            allow_isolated_qa=args.isolated_qa
        )
    except Exception as exc:
        # Do not log connection strings, database error messages, or credentials.
        raise SystemExit("HISTORY_CATALOG_PREFLIGHT_BLOCKED:" +
                         type(exc).__name__) from None
    serialized = json.dumps(report,indent=2,sort_keys=True) + "\n"
    if args.output:
        from pathlib import Path
        path=Path(args.output).expanduser()
        path.parent.mkdir(parents=True,exist_ok=True)
        with open(path,"w",encoding="utf-8") as output:
            output.write(serialized)
        os.chmod(path,0o600)
        print("HISTORY_CATALOG_READONLY_REPORT_WRITTEN=" + str(path))
    else:
        print(serialized,end="")


if __name__ == "__main__":
    main()
