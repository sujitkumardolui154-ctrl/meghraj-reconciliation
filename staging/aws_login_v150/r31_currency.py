"""DB-R31 staging output: integer paise in PostgreSQL, rupees in user reports.

Never present internal 11800 paise as ₹11,800. All money conversion is exact
integer arithmetic; CSV values contain numeric rupee text without currency
symbols so Excel may interpret amount columns as numeric quantities.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation

from r31_db_r31_source_report_contract import csv_safe


def amount_rupees(paise: int | None) -> str | None:
    if paise is None:
        return None
    if type(paise) is not int:
        raise ValueError("PAISE_MUST_BE_EXACT_INTEGER")
    if abs(paise) > 10**16:
        raise ValueError("PAISE_AMOUNT_OUT_OF_RANGE")
    return f"{Decimal(paise) / Decimal(100):.2f}"


def amount_display(paise: int | None) -> str | None:
    rupees=amount_rupees(paise)
    return None if rupees is None else f"₹{rupees}"


def group_to_public(row: dict) -> dict:
    """Do not leak raw paise into INR-labeled output fields."""
    credit=row["received_credit_paise"]
    matched=row.get("verified_allocated_paise")
    return {
        "sol_id":row.get("raw_sol",""),
        "official_branch_name":row.get("official_branch_name",""),
        "sol_master_sha256":row.get("sol_master_sha256"),
        "uploaded_source_rows":int(row["uploaded_source_rows"]),
        "valid_received_rows":int(row["valid_received_rows"]),
        "credit_received_rupees":amount_rupees(credit),
        "credit_received_display":amount_display(credit),
        "held_rows":int(row["held_rows"]),
        "excluded_invalid_rows":int(row["excluded_invalid_rows"]),
        "pending_reconciliation_rows":int(row["pending_reconciliation_rows"]),
        "legacy_unclassified_rows":int(row["legacy_unclassified_rows"]),
        "verified_matched_payment_rows":row.get("verified_matched_payment_rows"),
        "verified_allocated_rupees":amount_rupees(matched),
        "reconciliation_status":"NOT_CALCULATED",
    }


def detail_to_public(row: dict) -> dict:
    return {
        "source_receipt_id":row.get("source_receipt_id"),
        "source_sha256":row.get("source_sha256"),
        "source_sheet_name":row.get("source_sheet_name"),
        "source_row_number":row.get("source_row_number"),
        "description":row.get("description"),
        "sol_id":row.get("raw_sol"),
        "original_credit_amount":row.get("raw_credit_amount"),
        "credit_amount_rupees":amount_rupees(row.get("credit_paise")),
        "credit_amount_display":amount_display(row.get("credit_paise")),
        "official_branch_name":row.get("official_branch_name"),
        "source_status":row.get("source_status"),
        "reason_codes":row.get("reason_codes"),
        "reconciliation_status":"NOT_CALCULATED",
        "verified_invoice_refs":None,
    }


SOL_CSV_HEADERS=(
    "SOL ID","Official Branch Name","Uploaded Source Rows",
    "Valid Received Rows","Credit Received (INR)","Held Rows",
    "Excluded Invalid Rows","Pending Reconciliation Rows",
    "Reconciliation Status",
)
SOL_CSV_KEYS=(
    "sol_id","official_branch_name","uploaded_source_rows",
    "valid_received_rows","credit_received_rupees","held_rows",
    "excluded_invalid_rows","pending_reconciliation_rows",
    "reconciliation_status",
)
DETAIL_CSV_HEADERS=(
    "Receipt ID","Source Row","Description","SOL ID","Original Credit Amount",
    "Credit Amount (INR)","Official Branch Name","Source Status",
    "Reconciliation Status",
)
DETAIL_CSV_KEYS=(
    "source_receipt_id","source_row_number","description","sol_id",
    "original_credit_amount","credit_amount_rupees","official_branch_name",
    "source_status","reconciliation_status",
)


def public_csv(rows, *, detail=False) -> bytes:
    import csv
    import io
    headers=DETAIL_CSV_HEADERS if detail else SOL_CSV_HEADERS
    keys=DETAIL_CSV_KEYS if detail else SOL_CSV_KEYS
    buff=io.StringIO(newline="")
    writer=csv.writer(buff,lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([
            csv_safe(row.get(key)) if row.get(key) is not None else ""
            for key in keys
        ])
    return buff.getvalue().encode("utf-8-sig")
