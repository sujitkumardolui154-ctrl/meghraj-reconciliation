
import csv
import io
import logging
from flask import jsonify, Response
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

SHA = "433762732cc219210a70956e58020e8e786dd89f78c51538db45878f465a1ea1"
DATASET = SHA + "-report-v1"
REPORTS = {
    "unpaid": ("unpaid_payment", True, 2430),
    "ok": ("source_ok", True, 178),
    "balance-review": ("balance_valid", False, 1384),
}
COLUMNS = [
    "invoice_no", "model_sol_id", "client_name",
    "invoice_date", "invoice_month", "bill_amount_source",
    "payment_received_source", "outstanding_amount",
    "outstanding_source", "balance_issue", "source_status",
    "status_basis", "balance_basis", "sol_source_type",
    "source_sheet", "source_row", "source_sha256",
]

def csv_cell(value):
    text = "" if value is None else str(value)
    # Prevent spreadsheet formula execution in exported text.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text

def handle_snapshot_reports(request):
    if request.method != "GET":
        return jsonify(error="Method not allowed"), 405
    path = request.path.rstrip("/")
    kind = None
    if path != "/reports":
        name = path.removeprefix("/reports/")
        if not name.endswith(".csv") or name[:-4] not in REPORTS:
            return jsonify(error="Unknown report"), 404
        kind = name[:-4]

    try:
        db = firestore.Client(project="meghraj-reconciliation")
        ref = db.collection("dashboard_report_datasets").document(DATASET)
        snapshot = ref.get(timeout=15)
        metadata = snapshot.to_dict() or {}
        if (
            metadata.get("state") != "READY"
            or metadata.get("unpaid_payment_state") != "READY"
            or metadata.get("unpaid_payment_count") != 2430
            or metadata.get("unpaid_payment_basis")
                != "PAYMENT_RECEIVED_COLUMN_U_BLANK_OR_ZERO"
            or metadata.get("source_sha256") != SHA
            or metadata.get("rows") != 14374
        ):
            return jsonify(error="Report snapshot is not ready"), 503

        # Original 53-column CSV export
        headers = metadata.get("original_headers")
        if (
            metadata.get("original_columns_state") != "READY"
            or metadata.get("original_column_count") != 53
            or metadata.get("original_columns_row_count") != 14374
            or headers != HEADERS_53
        ):
            return jsonify(error="Original report columns are not ready"), 503

        if kind is None:
            response = jsonify(
                version="1.3.0",
                dataset=DATASET,
                source="Imported workbook snapshot",
                reconciliation_executed=False,
                reports={
                    name: {"rows": spec[2], "url": "/reports/" + name + ".csv"}
                    for name, spec in REPORTS.items()
                },
                login_report="EVENT_LOGGING_NOT_CONNECTED",
                failure_report="EVENT_LOGGING_NOT_CONNECTED",
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        field, value, expected = REPORTS[kind]
        documents = (
            ref.collection("rows")
            .where(filter=FieldFilter(field, "==", value))
            .limit(expected + 1)
            .get(timeout=60, retry=None)
        )
        rows = [document.to_dict() for document in documents]
        if len(rows) != expected:
            return jsonify(error="Report row count mismatch; export stopped"), 503
        if any(
            row.get("source_sha256") != SHA
            or row.get(field) is not value
            or not isinstance(row.get("source_row"), int)
            for row in rows
        ):
            return jsonify(error="Report source validation failed"), 503

        for row in rows:
            values = row.get("original_values")
            if (
                row.get("original_columns_source_sha256") != SHA
                or not isinstance(values, list)
                or len(values) != 53
                or not all(isinstance(value, str) for value in values)
            ):
                return jsonify(error="Original row values are incomplete"), 503

        rows.sort(key=lambda row: row["source_row"])
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([csv_cell(value) for value in row["original_values"]])

        return Response(
            output.getvalue().encode("utf-8-sig"),
            content_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="sbi-' + kind + '-v1.3.0.csv"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Report-Rows": str(len(rows)),
            },
        )
    except Exception:
        logging.exception("Database report export failed")
        return jsonify(error="Database report unavailable; check server logs"), 503


# DIL reports: completed monthly imports
import hashlib
import re
from flask import current_app
from invoice_source_schema import HEADERS_53, row_layout, export_values_53
from invoice_import_store import invoice_fields
from report_source_integrity import (
    validate_receipt_source_positions,
    validate_completed_receipt_source_sheet,
)


def completed_import_rows(db):
    documents = db.collection("dashboard_invoice_rows_v140").get(
        timeout=60, retry=None
    )
    candidates = []
    receipt_ids = set()
    for document in documents:
        row = document.to_dict()
        receipt = row.get("import_receipt", "")
        if not isinstance(receipt, str) or not re.fullmatch(
            r"[a-f0-9]{32}", receipt
        ):
            raise ValueError("Imported invoice has an invalid receipt")
        candidates.append((document.id, row))
        receipt_ids.add(receipt)

    receipts = {}
    ids = sorted(receipt_ids)
    for start in range(0, len(ids), 100):
        refs = [
            db.collection("dashboard_import_receipts_v140").document(rid)
            for rid in ids[start:start + 100]
        ]
        for snapshot in db.get_all(refs, timeout=30):
            if not snapshot.exists:
                raise ValueError("Imported invoice receipt is missing")
            receipts[snapshot.id] = snapshot.to_dict()
    if set(receipts) != receipt_ids:
        raise ValueError("Incomplete import receipt response")

    groups = {}
    for document_id, row in candidates:
        groups.setdefault(row["import_receipt"], []).append((document_id, row))

    result = []
    for rid, entries in groups.items():
        receipt = receipts[rid]
        if receipt.get("status") != "COMPLETED":
            # In-progress or interrupted imports become reportable on completion.
            continue
        total = receipt.get("total_count")
        added = receipt.get("added_count")
        rejected = receipt.get("rejected_count")
        processed = receipt.get("processed_count")
        if (
            any(type(v) is not int or v < 0
                for v in (total, added, rejected, processed))
            or added + rejected != total
            or processed != total
            or len(entries) != added
            or receipt.get("finance_processed") is not False
        ):
            raise ValueError("Completed import counts are inconsistent")

        # Completed receipts must map each physical source worksheet row once.
        # Fail closed before any report content is returned.
        validate_receipt_source_positions(entries)
        validate_completed_receipt_source_sheet(receipt, entries)

        for document_id, row in entries:
            width, invoice_index, _, _, source_headers = row_layout(row)
            values = row["original_values"]
            invoice = values[invoice_index]
            if document_id != hashlib.sha256(invoice.encode("utf-8")).hexdigest():
                raise ValueError("Imported invoice key mismatch")
            if row.get("invoice_no") != invoice:
                raise ValueError("Imported invoice number mismatch")
            source_hash = row.get("source_sha256", "")
            if (
                not isinstance(source_hash, str)
                or not re.fullmatch(r"[a-f0-9]{64}", source_hash)
                or source_hash != receipt.get("source_sha256")
                or row.get("source_sheet") != receipt.get("source_sheet")
                or type(row.get("source_row")) is not int
                or row["source_row"] < 2
                or row.get("finance_processed") is not False
            ):
                raise ValueError("Imported invoice source mismatch")
            if receipt.get("source_headers", source_headers) != source_headers:
                raise ValueError("Import receipt header mismatch")

            derived = invoice_fields(
                row, rid, source_hash, row["source_sheet"]
            )
            for field in ("unpaid_payment", "source_ok", "balance_valid"):
                if row.get(field) is not derived[field]:
                    raise ValueError("Imported report filter mismatch")

            export_values = export_values_53(row)
            result.append({
                **row,
                "export_values": export_values,
            })

    result.sort(key=lambda row: (row["import_receipt"], row["source_row"]))
    return result



# DIL payment reports v1.4.2
from payment_report_rules import payment_report_kind

PAYMENT_REPORTS = ("unpaid", "ok", "error-value")
REPORT_NAMES_V142 = PAYMENT_REPORTS + ("balance-review",)

def load_report_rows_v142(db):
    ref = db.collection("dashboard_report_datasets").document(DATASET)
    metadata = ref.get(timeout=15).to_dict() or {}
    if (
        metadata.get("state") != "READY"
        or metadata.get("source_sha256") != SHA
        or metadata.get("rows") != 14374
        or metadata.get("original_columns_state") != "READY"
        or metadata.get("original_column_count") != 53
        or metadata.get("original_columns_row_count") != 14374
        or metadata.get("original_headers") != HEADERS_53
    ):
        raise ValueError("Baseline source metadata is incomplete")

    documents = []
    query = ref.collection("rows").order_by("__name__")
    cursor = None
    while True:
        page_query = query.limit(100)
        if cursor is not None:
            page_query = page_query.start_after(cursor)
        from google.api_core.retry import Retry, if_transient_error
        page = page_query.get(
            timeout=30,
            retry=Retry(
                predicate=if_transient_error,
                initial=1.0,
                maximum=5.0,
                multiplier=2.0,
                timeout=60.0,
            ),
        )
        if not page:
            break
        documents.extend(page)
        logging.info("Baseline report read: %s rows", len(documents))
        if len(documents) > 14374:
            raise ValueError("Unexpected extra baseline rows")
        cursor = page[-1]
        if len(page) < 100:
            break
    baseline = []
    source_rows = set()
    for document in documents:
        row = document.to_dict()
        values = row.get("original_values")
        number = row.get("source_row")
        if (
            row.get("source_sha256") != SHA
            or row.get("original_columns_source_sha256") != SHA
            or type(number) is not int
            or number in source_rows
            or not isinstance(values, list)
            or len(values) != 53
            or not all(isinstance(value, str) for value in values)
            or type(row.get("balance_valid")) is not bool
        ):
            raise ValueError("Baseline source row is invalid")
        source_rows.add(number)
        baseline.append({
            **row,
            "export_values": list(values),
            "payment_report": payment_report_kind(row),
        })

    if source_rows != set(range(2, 14376)):
        raise ValueError("Baseline source rows are incomplete")
    baseline.sort(key=lambda row: row["source_row"])

    # Existing receipt, source and invoice-key checks remain in use.
    imported = completed_import_rows(db)
    for row in imported:
        row["payment_report"] = payment_report_kind(row)
    return baseline, imported

def report_groups_v142(rows):
    groups = {name: [] for name in REPORT_NAMES_V142}
    for row in rows:
        groups[row["payment_report"]].append(row)
        if row["balance_valid"] is False:
            groups["balance-review"].append(row)
    if sum(len(groups[name]) for name in PAYMENT_REPORTS) != len(rows):
        raise ValueError("Payment report totals are inconsistent")
    return groups

def handle_reports(request):
    if request.method != "GET":
        return jsonify(error="Method not allowed"), 405

    path = request.path.rstrip("/")
    kind = None
    if path != "/reports":
        routes = {
            "/reports/" + name + ".csv": name
            for name in REPORT_NAMES_V142
        }
        kind = routes.get(path)
        if kind is None:
            return jsonify(error="Unknown report"), 404

    try:
        db = firestore.Client(project="meghraj-reconciliation")
        baseline, imported = load_report_rows_v142(db)
        base_groups = report_groups_v142(baseline)
        import_groups = report_groups_v142(imported)

        if kind is None:
            response = jsonify(
                version="1.4.2",
                dataset=DATASET,
                source="Original database snapshot plus completed invoice imports",
                reconciliation_executed=False,
                completed_import_rows=len(imported),
                total_invoice_rows=len(baseline) + len(imported),
                payment_report_basis="PAYMENT_RECEIVED_BLANK_ZERO_NUMERIC_OR_ERROR",
                reports={
                    name: {
                        "rows": len(base_groups[name]) + len(import_groups[name]),
                        "baseline_rows": len(base_groups[name]),
                        "imported_rows": len(import_groups[name]),
                        "url": "/reports/" + name + ".csv",
                    }
                    for name in REPORT_NAMES_V142
                },
                login_report="EVENT_LOGGING_NOT_CONNECTED",
                failure_report="EVENT_LOGGING_NOT_CONNECTED",
            )
        else:
            rows = base_groups[kind] + import_groups[kind]
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(HEADERS_53)
            for row in rows:
                values = row["export_values"]
                if len(values) != 53 or not all(
                    isinstance(value, str) for value in values
                ):
                    raise ValueError("Export values are incomplete")
                writer.writerow([csv_cell(value) for value in values])

            response = Response(
                output.getvalue().encode("utf-8-sig"),
                content_type="text/csv; charset=utf-8",
            )
            response.headers["Content-Disposition"] = (
                'attachment; filename="sbi-' + kind + '-v1.4.2.csv"'
            )
            response.headers["X-Report-Rows"] = str(len(rows))

        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        logging.exception("Payment report v1.4.2 export failed")
        response = jsonify(
            error="Report source could not be verified; export stopped"
        )
        response.status_code = 503
        response.headers["Cache-Control"] = "no-store"
        return response
