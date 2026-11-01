
"""Dashboard v1.4.0 atomic add-only invoice writer."""
import hashlib
import re
from decimal import Decimal, InvalidOperation
from google.cloud import firestore
from invoice_source_schema import row_layout

BASELINE_SHA = "433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"

def numeric_value(text, cell_type):
    if cell_type in ("e", "b"):
        return None
    try:
        value = Decimal(text.strip())
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None

def invoice_fields(row, receipt_id, source_sha, sheet):
    width, invoice_index, payment_index, balance_index, headers = row_layout(row)
    values = row.get("original_values")
    types = row.get("original_cell_types")
    if (
        not isinstance(values, list) or len(values) != width
        or not all(isinstance(v, str) for v in values)
        or not isinstance(types, list) or len(types) != width
        or not all(isinstance(v, str) for v in types)
    ):
        raise ValueError("Invalid staged invoice columns")

    invoice = values[invoice_index]
    if (
        not invoice or invoice != invoice.strip()
        or invoice.upper() in ("NA", "N/A")
        or types[invoice_index] != "s"
        or any(ord(c) < 32 for c in invoice)
    ):
        raise ValueError("Invalid staged invoice number")

    payment = numeric_value(values[payment_index], types[payment_index])
    payment_blank = not values[payment_index].strip() and types[payment_index] not in ("e", "b")
    balance = numeric_value(values[balance_index], types[balance_index])

    return {
        "invoice_no": invoice,
        "original_values": values,
        "original_cell_types": types,
        "original_headers": list(headers),
        "source_column_count": width,
        "source_sha256": source_sha,
        "source_sheet": sheet,
        "source_row": row["source_row"],
        "import_receipt": receipt_id,
        "unpaid_payment": payment_blank or payment == Decimal("0"),
        "payment_review": not payment_blank and payment is None,
        "source_ok": width == 53 and values[37] == "OK",
        "balance_valid": balance is not None,
        "status_basis": (
            "EXISTING_WORKBOOK_STATUS" if width == 53
            else "SOURCE_HAS_NO_RECONCILIATION_STATUS"
        ),
        "balance_basis": "EXCEL_SAVED_VALUE_NOT_RECALCULATED",
        "finance_processed": False,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

def apply_staged_row(db, receipt_id, row_id):
    if not re.fullmatch(r"[a-f0-9]{32}", receipt_id):
        raise ValueError("Invalid receipt")
    if not re.fullmatch(r"[0-9]{6}", row_id):
        raise ValueError("Invalid row ID")

    config_ref = db.collection("dashboard_import_config").document("v140")
    receipt_ref = db.collection("dashboard_import_receipts_v140").document(receipt_id)
    staged_ref = receipt_ref.collection("rows").document(row_id)

    @firestore.transactional
    def apply(transaction):
        config_snap = config_ref.get(transaction=transaction)
        receipt_snap = receipt_ref.get(transaction=transaction)
        staged_snap = staged_ref.get(transaction=transaction)

        if not config_snap.exists or not receipt_snap.exists or not staged_snap.exists:
            raise ValueError("Import configuration or staged row missing")

        config = config_snap.to_dict()
        receipt = receipt_snap.to_dict()
        row = staged_snap.to_dict()

        if row.get("status") in ("ADDED", "REJECTED"):
            return row["status"]

        if (
            config.get("state") != "READY"
            or config.get("imports_enabled") is not True
            or config.get("baseline_sha256") != BASELINE_SHA
        ):
            raise ValueError("Database imports are disabled")

        if receipt.get("status") != "APPLYING":
            raise ValueError("Receipt is not ready to apply")
        if row.get("status") != "READY_TO_ADD":
            raise ValueError("Row has not passed preview")
        if type(row.get("source_row")) is not int:
            raise ValueError("Invalid source row")
        if str(row["source_row"]).zfill(6) != row_id:
            raise ValueError("Staged row ID mismatch")

        source_sha = receipt.get("source_sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", source_sha):
            raise ValueError("Invalid source hash")
        sheet = receipt.get("source_sheet")
        if not isinstance(sheet, str) or not sheet:
            raise ValueError("Missing source sheet")

        fields = invoice_fields(row, receipt_id, source_sha, sheet)
        invoice = fields["invoice_no"]
        key = hashlib.sha256(invoice.encode("utf-8")).hexdigest()
        key_ref = db.collection("dashboard_invoice_keys_v140").document(key)
        key_snap = key_ref.get(transaction=transaction)

        if key_snap.exists:
            if key_snap.to_dict().get("invoice_no") != invoice:
                raise ValueError("Invoice index conflict")
            transaction.update(staged_ref, {
                "status": "REJECTED",
                "reasons": ["INVOICE_ALREADY_EXISTS"],
                "completed_at": firestore.SERVER_TIMESTAMP,
            })
            transaction.update(receipt_ref, {
                "rejected_count": firestore.Increment(1),
                "processed_count": firestore.Increment(1),
            })
            return "REJECTED"

        invoice_ref = db.collection("dashboard_invoice_rows_v140").document(key)
        transaction.create(invoice_ref, fields)
        transaction.create(key_ref, {
            "invoice_no": invoice,
            "origin": "MONTHLY_IMPORT",
            "import_receipt": receipt_id,
            "invoice_path": invoice_ref.path,
        })
        transaction.update(staged_ref, {
            "status": "ADDED",
            "reasons": [],
            "completed_at": firestore.SERVER_TIMESTAMP,
        })
        transaction.update(receipt_ref, {
            "added_count": firestore.Increment(1),
            "processed_count": firestore.Increment(1),
        })
        return "ADDED"

    return apply(db.transaction(max_attempts=5))
