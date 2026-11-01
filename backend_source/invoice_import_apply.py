"""DIL v1.4.0 resumable, add-only import application."""
import re
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from invoice_import_store import BASELINE_SHA, apply_staged_row

BATCH_SIZE = 10


def apply_import_batch(db, receipt_id):
    if not re.fullmatch(r"[a-f0-9]{32}", receipt_id):
        raise ValueError("Invalid receipt")

    config_ref = db.collection("dashboard_import_config").document("v140")
    receipt_ref = db.collection(
        "dashboard_import_receipts_v140"
    ).document(receipt_id)

    @firestore.transactional
    def transition(transaction, start):
        config_snapshot = config_ref.get(transaction=transaction)
        snapshot = receipt_ref.get(transaction=transaction)
        if not config_snapshot.exists or not snapshot.exists:
            raise ValueError("Import configuration or receipt missing")

        config = config_snapshot.to_dict()
        receipt = snapshot.to_dict()
        names = (
            "total_count", "ready_count", "added_count",
            "rejected_count", "processed_count",
        )
        for name in names:
            if type(receipt.get(name)) is not int or receipt[name] < 0:
                raise ValueError("Invalid import counters")

        total = receipt["total_count"]
        processed = receipt["processed_count"]
        added = receipt["added_count"]
        rejected = receipt["rejected_count"]
        if (
            total == 0 or processed > total
            or added + rejected != processed
            or receipt["ready_count"] > total
            or added > receipt["ready_count"]
            or receipt.get("finance_processed") is not False
            or receipt.get("version") != "1.4.0"
        ):
            raise ValueError("Import receipt consistency check failed")

        status = receipt.get("status")
        if status == "COMPLETED":
            if processed != total:
                raise ValueError("Completed receipt has incomplete counts")
        else:
            if (
                config.get("state") != "READY"
                or config.get("imports_enabled") is not True
                or config.get("baseline_sha256") != BASELINE_SHA
                or config.get("index_collection")
                    != "dashboard_invoice_keys_v140"
            ):
                raise ValueError("Database imports are disabled")

            if status not in ("PREVIEW_READY", "APPLYING"):
                raise ValueError("Receipt is not ready to apply")

            changes = {}
            if status == "PREVIEW_READY":
                if not start:
                    raise ValueError("Apply has not started")
                if added != 0 or receipt["ready_count"] + rejected != total:
                    raise ValueError("Preview counters are inconsistent")
                status = "APPLYING"
                changes["status"] = status
                changes["apply_started_at"] = firestore.SERVER_TIMESTAMP

            if processed == total:
                status = "COMPLETED"
                changes["status"] = status
                changes["completed_at"] = firestore.SERVER_TIMESTAMP

            if changes:
                transaction.update(receipt_ref, changes)

        return {
            "receipt": receipt_id,
            "version": "1.4.0",
            "status": status,
            "total": total,
            "added": added,
            "rejected": rejected,
            "remaining": total - processed,
            "finance_processed": False,
        }

    result = transition(db.transaction(max_attempts=5), True)
    if result["status"] == "COMPLETED":
        return result

    documents = (
        receipt_ref.collection("rows")
        .where(filter=FieldFilter("status", "==", "READY_TO_ADD"))
        .limit(BATCH_SIZE)
        .get(timeout=30, retry=None)
    )
    for document in documents:
        # Each row, uniqueness key and receipt counter commit atomically.
        # Repeated or concurrent calls do not add the same row twice.
        apply_staged_row(db, receipt_id, document.id)

    result = transition(db.transaction(max_attempts=5), False)
    if not documents and result["remaining"]:
        raise ValueError(
            "Import counters and staged rows disagree; inspect this receipt"
        )
    return result
