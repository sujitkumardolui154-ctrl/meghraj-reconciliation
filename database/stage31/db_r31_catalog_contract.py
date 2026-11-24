"""DB-R31.1: analyze READ-ONLY central catalog lines, never financial data."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

MAPPING = {
    "Description": {"target": "sbi.payments.description", "raw": "sbi.payment_source_rows.original_values",
                    "note": "original bank narration, not payment settlement"},
    "SOL ID": {"target": "sbi.payments.sol_id", "raw": "sbi.payment_source_rows.original_values",
               "note": "Excel TEXT; keep leading zeros, canonical SOL only for approved lookup"},
    "Credit Amount": {"target": "sbi.payments.credit_paise", "raw": "sbi.payment_source_rows.original_values",
                      "note": "positive exact integer paise, not allocated amount"},
    "Source row": {"target": "sbi.payment_source_rows.source_row_number",
                   "note": "physical original worksheet row number"},
    "Source file SHA": {"target": "sbi.import_batches.source_sha256",
                        "note": "needs owner-scoped source identity"},
}

REQUIRED = {
    "import_batches": ("id", "source_system", "source_kind", "source_sha256"),
    "payment_source_rows": ("id", "batch_id", "source_row_number", "original_values", "row_sha256"),
    "payments": ("id", "source_row_id", "description", "sol_id", "credit_paise"),
}

def catalog_to_contract(text: str) -> dict:
    lines = text.splitlines()
    if "DB_R31_CATALOG_BEGIN|sbi_reconciliation_main" not in lines:
        raise ValueError("WRONG_CENTRAL_DATABASE")
    if "DB_R31_CATALOG_END|READ_ONLY" not in lines:
        raise ValueError("INCOMPLETE_READ_ONLY_CATALOG")
    columns = {}
    owners = []
    roles = []
    unique = False
    constraints = []
    for line in lines:
        parts = line.strip().split("|")
        kind = parts[0]
        if kind == "COLUMN" and len(parts) >= 7:
            if not parts[2].isdigit():
                raise ValueError("INVALID_CATALOG_COLUMN_ORDINAL")
            columns.setdefault(parts[1], {})[parts[3]] = parts[4]
        elif kind == "OWNER_FIELD":
            owners.append(parts)
        elif kind == "REPORT_ROLE":
            roles.append(parts)
        elif kind == "GLOBAL_FILE_SHA_UNIQUE" and len(parts) > 1:
            unique = unique or parts[1] == "PRESENT_REVIEW_REQUIRED_FOR_MULTITENANT"
        elif kind == "CONSTRAINT":
            constraints.append(parts)
    missing = {table: [c for c in required if c not in columns.get(table,{})]
               for table, required in REQUIRED.items()}
    missing = {table: fields for table, fields in missing.items() if fields}
    owner = any(x[1] == "import_batches" and
                ("owner_uid=PRESENT" in x or "tenant_id=PRESENT" in x)
                for x in owners if len(x) > 1)
    unexpected = sorted(set(x[1] for x in roles if any(
        v in ("INSERT=true", "UPDATE=true", "DELETE=true",
              "INSERT=t", "UPDATE=t", "DELETE=t") for v in x[2:]
    )))
    risks = []
    if missing:
        risks.append("CENTRAL_SOURCE_FIELD_MAPPING_UNVERIFIED")
    if not owner:
        risks.append("OWNER_SCOPED_BATCH_IDENTITY_UNVERIFIED")
    if unique:
        risks.append("GLOBAL_SHA_UNIQUE_COLLIDES_FOR_MULTIPLE_OWNERS")
    if unexpected:
        risks.append("REPORT_ROLE_WRITE_GRANT_DETECTED")
    for requirement in (
        "INVALID_ROWS_AND_REASONS_NEED_VERSIONED_OWNER_SCOPED_EVIDENCE",
        "APPROVED_CURRENT_SOL_BRANCH_MASTER_SHA_NOT_VERIFIED",
        "AUTHENTICATED_OWNER_SCOPED_REPORT_PARITY_NOT_VERIFIED",
        "FULL_VERIFIED_RECONCILIATION_ALLOCATIONS_NOT_CONNECTED",
        "PRODUCTION_SOURCE_WRITE_SCOPE_NOT_APPROVED",
    ):
        risks.append(requirement)
    return {
        "deliverable": "DB_R31_SCHEMA_DIFF_AND_TABLE_MAP",
        "target": "sbi_reconciliation_main",
        "no_new_primary_db": True,
        "status": "DESIGNED_CATALOG_REVIEW_REQUIRED",
        "production_financial_writes": False,
        "financial_values_read": False,
        "tables": sorted(columns),
        "table_columns": columns,
        "missing_required_source_columns": missing,
        "owner_scoped_batch_column_observed": owner,
        "global_file_sha_unique_observed": unique,
        "report_role_write_grants": unexpected,
        "report_role_matrix": roles,
        "constraint_count": len(constraints),
        "source_to_central_contract": MAPPING,
        "risk_and_review": risks,
        "next_required": "REVIEWED_OWNER_SCOPED_ADDITIVE_MIGRATION_AND_ISOLATED_QA",
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("catalog", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    output = catalog_to_contract(a.catalog.read_text(encoding="utf-8"))
    if a.output:
        a.output.write_text(json.dumps(output, indent=2, ensure_ascii=False)+"\n",encoding="utf-8")
    print("DB_R31_SCHEMA_CONTRACT="+output["status"])
    print("DB_R31_OWNER_SCOPE="+("COLUMN_SEEN_REQUIRES_REVIEW" if output["owner_scoped_batch_column_observed"] else "REVIEW_REQUIRED"))
    print("DB_R31_GLOBAL_SHA_COLLISION="+("YES" if output["global_file_sha_unique_observed"] else "INDEX_REVIEW_REQUIRED"))
    print("DB_R31_REPORT_ROLE_WRITE_GRANTS="+("REVIEW_REQUIRED" if output["report_role_write_grants"] else "NONE_DETECTED"))
    print("DB_R31_REQUIRED_SOURCE_MAPPING_GAPS="+str(len(output["missing_required_source_columns"])))
    print("DB_R31_PRODUCTION_WRITE_SCOPE=NOT_APPROVED")

if __name__ == "__main__":
    main()
