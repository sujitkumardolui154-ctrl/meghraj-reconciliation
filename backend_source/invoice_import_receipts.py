from invoice_source_schema import invoice_number

"""Dashboard v1.4.0 persistent import previews and rejection logs."""
import hashlib
import uuid
from pathlib import PurePosixPath
from google.cloud import firestore
from invoice_import_preview import build_preview
from invoice_change_report import generate_change_report
from invoice_import_store import BASELINE_SHA

BUCKET = "meghraj-sbi-uploads-109590290120"

def create_preview(db, storage_client, filename, data):
    config = db.collection("dashboard_import_config").document("v140").get(
        timeout=30
    ).to_dict() or {}
    if (
        config.get("state") != "READY"
        or config.get("baseline_sha256") != BASELINE_SHA
    ):
        raise ValueError("Invoice uniqueness index is not ready")

    # Parse and reject duplicates within this file before database matching.
    preview = build_preview(filename, data, set())
    candidates = preview["accepted"]
    rejected = preview["rejected"]
    accepted = []
    keys = db.collection("dashboard_invoice_keys_v140")

    for start in range(0, len(candidates), 200):
        chunk = candidates[start:start + 200]
        refs = []
        for row in chunk:
            invoice = invoice_number(row)
            key = hashlib.sha256(invoice.encode("utf-8")).hexdigest()
            refs.append(keys.document(key))

        snapshots = {
            doc.id: doc for doc in db.get_all(refs, timeout=60)
        }
        for row, ref in zip(chunk, refs):
            snapshot = snapshots.get(ref.id)
            if snapshot is None:
                raise ValueError("Incomplete invoice index response")
            invoice = invoice_number(row)
            if snapshot.exists:
                if snapshot.to_dict().get("invoice_no") != invoice:
                    raise ValueError("Invoice index conflict")
                rejected.append({
                    "source_row": row["source_row"],
                    "invoice_no": invoice,
                    "reasons": ["INVOICE_ALREADY_EXISTS"],
                })
            else:
                accepted.append(row)

    rejected.sort(key=lambda row: row["source_row"])
    total = len(accepted) + len(rejected)
    if total == 0:
        raise ValueError("No invoice rows found")

    # Separate audit includes existing duplicates and parser rejections.
    from invoice_excel_parser import parse_excel
    from report_api import load_report_rows_v142
    from change_feature import change_report
    parsed_audit = parse_excel(filename, data)
    baseline_audit, imported_audit = load_report_rows_v142(db)
    audit = change_report(baseline_audit + imported_audit,
                          parsed_audit["rows"], parsed_audit["rejected"])
    if audit["total"] != total:
        raise ValueError("Audit/upload total mismatch")

    receipt_id = uuid.uuid4().hex
    source_sha = hashlib.sha256(data).hexdigest()
    object_name = (
        "database-imports/" + receipt_id
        + PurePosixPath(filename).suffix.lower()
    )
    receipt = db.collection("dashboard_import_receipts_v140").document(receipt_id)
    receipt.create({
        "receipt": receipt_id,
        "version": "1.4.0",
        "status": "STAGING",
        "filename": filename,
        "source_sha256": source_sha,
        "source_sheet": preview["sheet"],
        "source_headers": preview["headers"],
        "source_column_count": len(preview["headers"]),
        "source_bucket": BUCKET,
        "source_object": object_name,
        "total_count": total,
        "ready_count": len(accepted),
        "added_count": 0,
        "rejected_count": len(rejected),
        "processed_count": len(rejected),
        "finance_processed": False,
        "created_at": firestore.SERVER_TIMESTAMP,
    }, timeout=30)

    try:
        # Keep the uploaded workbook as the import's source backup.
        storage_client.bucket(BUCKET).blob(object_name).upload_from_string(
            data,
            content_type="application/octet-stream",
            if_generation_match=0,
            timeout=60,
        )

        records = []
        for row in accepted:
            records.append({
                **row,
                "invoice_no": invoice_number(row),
                "status": "READY_TO_ADD",
                "reasons": [],
            })
        for row in rejected:
            records.append({
                **row,
                "status": "REJECTED",
            })

        identifiers = [str(row["source_row"]).zfill(6) for row in records]
        if len(set(identifiers)) != total:
            raise ValueError("Duplicate source row identifiers")

        for start in range(0, total, 100):
            batch = db.batch()
            for row in records[start:start + 100]:
                row_id = str(row["source_row"]).zfill(6)
                batch.create(
                    receipt.collection("rows").document(row_id),
                    {**row, "receipt": receipt_id},
                )
            batch.commit(timeout=60)

        # Immutable receipt-linked audit, stored before preview is marked ready.
        for start in range(0, audit["total"], 100):
            batch = db.batch()
            for item in audit["details"][start:start + 100]:
                row_id = str(item["source_row"]).zfill(6)
                batch.create(receipt.collection("change_audit").document(row_id), item)
            batch.commit(timeout=60)
        receipt.update({
            "change_audit_state": "READY",
            "change_audit_total": audit["total"],
            "change_audit_summary": audit["summary"],
            "change_audit_breakdown": audit["report_breakdown"],
        }, timeout=30)
        receipt.update({
            "status": "PREVIEW_READY",
            "preview_completed_at": firestore.SERVER_TIMESTAMP,
        }, timeout=30)
    except Exception:
        try:
            receipt.update({"status": "STAGING_FAILED"}, timeout=30)
        except Exception:
            pass
        raise RuntimeError(
            "Preview staging failed; receipt=" + receipt_id
        ) from None

    return {
        "receipt": receipt_id,
        "status": "PREVIEW_READY",
        "total": total,
        "ready_to_add": len(accepted),
        "rejected": len(rejected),
        "added": 0,
        "finance_processed": False,
    }
