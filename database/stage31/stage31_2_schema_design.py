"""Stage 31.2 - read-only source-to-Postgres schema mapper.

Only an unapproved candidate crosswalk is produced. No SQL write or financial
source values are accepted. Source header ordinals are preserved because
"Client Name" and "Branch Code" appear more than once.
"""
from __future__ import annotations
import json
import re
from invoice_source_schema import HEADERS_34, HEADERS_35, HEADERS_53

# Source ordinals are ZERO-BASED. Do not infer customer identity from duplicated
# Client Name or derive SOL from model-only columns.
SOURCE_COLUMNS = {
    34: {"invoice_no":9, "invoice_branch":2, "month":4,
         "invoice_date":5, "branch_code_primary":6, "taxable_amount":10,
         "cgst":11, "sgst":12, "total_bill_amount":13},
    35: {"invoice_no":10, "invoice_branch":2, "month":4,
         "invoice_date":5, "branch_code_primary":6,
         "branch_code_secondary":8,"taxable_amount":11,
         "cgst":12, "sgst":13, "total_bill_amount":14},
    53: {"invoice_no":12, "invoice_branch":2, "month":4,
         "invoice_date":5, "branch_code_primary":6,
         "branch_code_secondary":10, "taxable_amount":13,
         "cgst":14, "sgst":15, "total_bill_amount":16}
}
HEADERS = {34:HEADERS_34,35:HEADERS_35,53:HEADERS_53}

# Exact, conservative candidate-name dictionary; this NEVER selects one.
TARGET_CANDIDATES = {
    "invoice_no": ("invoice_no","invoice_number"),
    "invoice_branch": ("invoice_branch",),
    "month": ("service_month","month"),
    "invoice_date": ("invoice_date",),
    "branch_code_primary": ("branch_code","sol_id"),
    "branch_code_secondary": ("second_branch_code","branch_code_secondary"),
    "taxable_amount": ("taxable_amount",),
    "cgst": ("cgst",),
    "sgst": ("sgst",),
    "total_bill_amount": ("total_bill_amount","gross_amount"),
}
METADATA_CANDIDATES = {
    "source_workbook_sha256":("source_sha256","source_file_sha256"),
    "source_sheet":("source_sheet",),
    "source_row":("source_row",),
    "source_original_values":("original_values","source_payload","source_json"),
    "ingestion_receipt":("receipt_id","import_receipt_id","import_batch_id"),
}

def catalog_to_mapping(catalog):
    """Plan a crosswalk without assuming column semantics or uniqueness."""
    if not isinstance(catalog,dict) or catalog.get("database")!="sbi_reconciliation_main":
        raise ValueError("UNEXPECTED_DATABASE")
    tables=catalog.get("tables",{})
    if not isinstance(tables,dict):
        raise ValueError("INVALID_CATALOG")
    if "invoices" not in tables or "payments" not in tables:
        raise ValueError("REQUIRED_FINANCIAL_TABLES_MISSING")
    if not all(isinstance(v,list) for v in tables.values()):
        raise ValueError("INVALID_CATALOG_TABLE_LAYOUT")
    invoice_columns={}
    for c in tables["invoices"]:
        name=c.get("name")
        if not isinstance(name,str) or name in invoice_columns:
            raise ValueError("INVALID_OR_DUPLICATED_INVOICE_COLUMN")
        invoice_columns[name.lower()]={
            "actual_name":name,
            "sql_data_type":c.get("data_type"),
            "nullable":c.get("nullable"),
        }
    crosswalk={}
    for width,source in SOURCE_COLUMNS.items():
        entries=[]
        for field,index in source.items():
            cands=[dict(invoice_columns[name],target_name=name)
                   for name in TARGET_CANDIDATES[field] if name in invoice_columns]
            entries.append({
                "logical_field":field,
                "source_zero_based_index":index,
                "source_header_exact":HEADERS[width][index],
                "database_candidates":cands,
                "binding_state":"UNAPPROVED_REVIEW_REQUIRED",
            })
        crosswalk[str(width)] = entries

    metadata={}
    for key,candidates in METADATA_CANDIDATES.items():
        metadata[key]=[
            dict(invoice_columns[name],target_name=name)
            for name in candidates if name in invoice_columns
        ]
    indexes=catalog.get("indexes",[])
    # A unique index is a necessary check but not sufficient to authorize
    # writer idempotency. In particular, partial indexes/composite keys need review.
    unique_indexes=[
        {"table":x.get("table"),"index":x.get("index"),
         "definition":x.get("definition")}
        for x in indexes if x.get("table")=="invoices" and x.get("unique")
    ]
    reasons=[
        "DO_NOT_AUTO_SELECT_COLUMN_CANDIDATES",
        "DUPLICATE_CLIENT_NAME_HEADERS_REQUIRE_SOURCE_IDENTITY_REVIEW",
        "BANK_PAYMNENT_ORIGINAL_A_TO_L_AND_TRANSACTION_KEY_NOT_YET_VERIFIED",
        "CREDIT_AMOUNT_IS_NOT_PAYMENT_SETTLEMENT",
        "DATABASE_UNIQUE_INVOICE_KEY_AND_ATOMIC_RECEIPT_NOT_YET_APPROVED",
        "REQUIRE_SYNTHETIC_POSTGRES_TRANSACTION_ROLLBACK_QA_BEFORE_WRITE_ROLE",
    ]
    if not invoice_columns.get("invoice_no") and not invoice_columns.get("invoice_number"):
        reasons.append("NO_OBVIOUS_INVOICE_NUMBER_TARGET_COLUMN")
    if not unique_indexes:
        reasons.append("NO_UNIQUE_INVOICE_INDEX_VISIBLE_REVIEW_SCHEMA_CONSTRAINTS")
    return {
        "version":"STAGE31_2_SOURCE_TO_POSTGRES_CANDIDATES",
        "status":"REVIEW_REQUIRED_NO_WRITE_AUTHORITY",
        "database":catalog["database"],
        "table_names":sorted(tables),
        "invoice_source_ordinals":crosswalk,
        "invoice_target_columns":invoice_columns,
        "invoice_metadata_candidates":metadata,
        "invoice_unique_indexes_needing_review":unique_indexes,
        "payment_target_column_names":sorted(
            c.get("name") for c in tables["payments"] if isinstance(c.get("name"),str)),
        "bank_source_column_i":"ORIGINAL_CREDIT_NEEDS_HEADER_AND_BANK_ROW_VERIFICATION",
        "payment_3_field_template":"PREVIEW_ONLY_NO_BANK_TRANSACTION_ID",
        "required_reviews":reasons,
        "production_database_writes_authorized":False,
        "financial_engine_enabled":False,
    }

def render_summary(report):
    lines=[
        "STAGE31_2_SOURCE_LAYOUTS=34,35,53",
        "STAGE31_2_INVOICE_TARGET_COLUMNS="+",".join(sorted(report["invoice_target_columns"])),
        "STAGE31_2_PAYMENT_TARGET_COLUMNS="+",".join(report["payment_target_column_names"]),
        "STAGE31_2_INVOICE_UNIQUE_INDEX_CANDIDATES="+str(len(report["invoice_unique_indexes_needing_review"])),
        "STAGE31_2_FIELD_MAP_APPROVAL=REVIEW_REQUIRED",
        "STAGE31_2_SOURCE_IDENTITY_PAYMENT=REVIEW_REQUIRED",
        "STAGE31_2_FINANCIAL_ENGINE=DISABLED",
        "STAGE31_2_DATABASE_WRITES=NONE",
    ]
    return "\n".join(lines)

def assert_safe_report(report):
    if report.get("production_database_writes_authorized") is not False:
        raise ValueError("REPORT_CANNOT_AUTHORIZE_WRITES")
    if report.get("financial_engine_enabled") is not False:
        raise ValueError("FINANCIAL_ENGINE_MUST_STAY_OFF")
    if report.get("status")!="REVIEW_REQUIRED_NO_WRITE_AUTHORITY":
        raise ValueError("MAPPING_MUST_REQUIRE_REVIEW")
    return True
