"""Read-only future Credit Note preview; no database import or approval."""
from credit_note_validation import audit_credit_note_rows, marker_classification
from invoice_source_schema import row_layout


def build_credit_note_import_preview(rows, *, approved_credit_note_numbers=None,
                                    approved_invoice_numbers=None,
                                    existing_replacement_invoice_numbers=None):
    """Preview a dedicated Credit Note file; every row needs Credit Note No."""
    result = audit_credit_note_rows(
        rows,
        existing_credit_note_numbers=approved_credit_note_numbers,
        approved_invoice_numbers=approved_invoice_numbers,
        existing_replacement_invoice_numbers=existing_replacement_invoice_numbers,
        require_credit_note_numbers=True,
    )
    summary = result["summary"]
    return {
        **result,
        "import_ready": False,  # The DB writer and approval gate do not exist yet.
        "release_status": "REVIEW_REQUIRED",
        "reason": "PRODUCTION_CREDIT_NOTE_WRITER_NOT_IMPLEMENTED",
        "database_changed": False,
        "validated_registers": summary["approved_registers"],
    }


def summarize_invoice_upload_credit_notes(parsed_rows):
    """Preview-only annotations for original 34/35/53 invoice uploads.

    Original invoice import decisions remain unchanged; these layouts have no
    dedicated Credit Note number, so no Credit Note import is authorized.
    """
    counts = {"CREDIT_NOTE": 0, "REVIEW": 0, "OTHER": 0}
    for row in parsed_rows:
        _, _, payment_index, _, _ = row_layout(row)
        state = marker_classification(row["original_values"][payment_index])
        counts[state] += 1
    return {
        "source_rows_reviewed": len(parsed_rows),
        "normal_or_dated_credit_note_count": counts["CREDIT_NOTE"],
        "wording_or_date_review_count": counts["REVIEW"],
        "other_payment_narration_count": counts["OTHER"],
        "credit_note_number_uniqueness": "NOT_TESTED_NO_DEDICATED_CN_NO_COLUMN",
        "credit_note_import_ready": False,
        "financial_writes": 0,
    }
