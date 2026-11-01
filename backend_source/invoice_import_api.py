
"""Authenticated Excel preview and import receipt API."""
import logging
import re
from flask import jsonify
from google.cloud import firestore, storage
from werkzeug.exceptions import RequestEntityTooLarge
from invoice_import_receipts import create_preview

PROJECT = "meghraj-reconciliation"
MAX_BYTES = 8 * 1024 * 1024

def reply(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

def handle_imports(request):
    path = request.path.rstrip("/")
    try:
        if path == "/imports/preview":
            if request.method != "POST":
                return reply({"error": "Method not allowed"}, 405)
            request.max_content_length = MAX_BYTES + 65536
            if request.content_length is None:
                return reply({"error": "Content length required"}, 411)
            if request.content_length > MAX_BYTES + 65536:
                return reply({"error": "Maximum file size is 8 MiB"}, 413)
            if request.mimetype != "multipart/form-data":
                return reply({"error": "Choose an Excel file"}, 415)
            files = request.files.getlist("file")
            if len(files) != 1 or set(request.files) != {"file"}:
                return reply({"error": "Choose exactly one Excel file"}, 400)

            uploaded = files[0]
            data = uploaded.stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return reply({"error": "Maximum file size is 8 MiB"}, 413)

            result = create_preview(
                firestore.Client(project=PROJECT),
                storage.Client(project=PROJECT),
                uploaded.filename or "",
                data,
            )
            return reply(result, 201)

        # DIL v1.4.0: bounded, resumable apply.
        apply_match = re.fullmatch(
            r"/imports/([a-f0-9]{32})/apply", path
        )
        if apply_match:
            if request.method != "POST":
                return reply({"error": "Method not allowed"}, 405)
            from invoice_import_apply import apply_import_batch
            result = apply_import_batch(
                firestore.Client(project=PROJECT),
                apply_match.group(1),
            )
            return reply(result)

        match = re.fullmatch(
            r"/imports/([a-f0-9]{32})(/rows)?", path
        )
        if not match:
            return reply({"error": "Unknown import endpoint"}, 404)
        if request.method != "GET":
            return reply({"error": "Method not allowed"}, 405)

        receipt_id, rows_suffix = match.groups()
        db = firestore.Client(project=PROJECT)
        ref = db.collection("dashboard_import_receipts_v140").document(receipt_id)
        snapshot = ref.get(timeout=30)
        if not snapshot.exists:
            return reply({"error": "Import receipt not found"}, 404)
        receipt = snapshot.to_dict()

        if not rows_suffix:
            fields = (
                "receipt", "version", "status", "filename",
                "source_sha256", "source_sheet", "total_count",
                "ready_count", "added_count", "rejected_count",
                "processed_count", "finance_processed", "created_at",
            )
            return reply({key: receipt.get(key) for key in fields})

        cursor = request.args.get("after", "0")
        if not re.fullmatch(r"[0-9]{1,6}", cursor):
            return reply({"error": "Invalid page cursor"}, 400)
        query = ref.collection("rows").order_by("source_row")
        if int(cursor):
            query = query.start_after({"source_row": int(cursor)})
        documents = query.limit(100).get(timeout=30, retry=None)
        rows = []
        for document in documents:
            row = document.to_dict()
            rows.append({
                "source_row": row["source_row"],
                "invoice_no": row.get("invoice_no", ""),
                "status": row.get("status"),
                "reasons": row.get("reasons", []),
            })
        return reply({
            "receipt": receipt_id,
            "rows": rows,
            "next_after": (
                rows[-1]["source_row"] if len(rows) == 100 else None
            ),
        })

    except RequestEntityTooLarge:
        return reply({"error": "Maximum file size is 8 MiB"}, 413)
    except ValueError as error:
        return reply({"error": str(error)}, 400)
    except Exception:
        logging.exception("Database import preview or receipt request failed")
        return reply({
            "error": "Import request failed. Check server logs before retrying."
        }, 503)
