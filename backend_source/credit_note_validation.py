"""Pure, read-only SBI Credit Note validation for future imports.

This module does not query or write Firestore. The caller must supply the
approved identity registers, and a preview is never equivalent to approval.
An invoice referenced by a Credit Note may legitimately already exist; it is
NOT an attempt to re-import that invoice into the invoice ledger.
"""
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
import re

DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %m %Y",
    "%Y-%m-%d", "%d-%B-%Y", "%d-%b-%Y", "%d %B %Y",
    "%d %b %Y", "%B %Y", "%b %Y",
)
MARKER = re.compile(r"^CREDIT\s+NOTE(?:\s*@?\s*(?P<date>.*))?$", re.I)
MXP_REFERENCE = re.compile(r"^MXP(?=[A-Z0-9/_-]*[A-Z0-9])[A-Z0-9/_-]+$")
INVOICE_ALIASES = ("Invoice No", "Invoice Number")
CREDIT_NOTE_ALIASES = ("Credit Note No", "Credit Note Number")
REPLACEMENT_ALIASES = (
    "New Invoice Against Credit Note",
    "New Invoice Agansit of Credit Note",  # Historical source spelling
)
NARRATION_ALIASES = (
    "Payment Received (If With GST or Excluding GST)",
    "Payment Received ( If With GST or Excluding GST)",
    "Credit Note Description",
)


def text(value):
    return " ".join(str(value if value is not None else "").strip().split())


def number(value):
    return text(value).upper()


def valid_mxp_reference(value):
    return bool(MXP_REFERENCE.fullmatch(number(value)))


def marker_classification(value):
    """CREDIT_NOTE, REVIEW, or OTHER; malformed dates must not auto-approve."""
    value = text(value)
    if not value:
        return "OTHER"
    m = MARKER.fullmatch(value)
    if m:
        date_text = m.group("date")
        if not date_text or not date_text.strip():
            return "REVIEW" if "@" in value else "CREDIT_NOTE"
        for fmt in DATE_FORMATS:
            try:
                datetime.strptime(date_text.strip(), fmt)
                return "CREDIT_NOTE"
            except ValueError:
                continue
        return "REVIEW"
    if value.upper().startswith(("CREDIT NOTE", "CREDITE NOTE", "CREDIT NORTE")):
        return "REVIEW"
    return "OTHER"


def is_credit_note_marker(value):
    return marker_classification(value) == "CREDIT_NOTE"


def _field(row, aliases):
    present = [k for k in aliases if k in row]
    if len(present) > 1:
        raise ValueError("Ambiguous duplicated field aliases: " + ", ".join(present))
    return row.get(present[0]) if present else None


def _present(row, aliases):
    return any(k in row for k in aliases)


def audit_credit_note_rows(
    rows: Iterable[Mapping], *,
    existing_credit_note_numbers=None,
    approved_invoice_numbers=None,
    existing_replacement_invoice_numbers=None,
    require_credit_note_numbers=True,
):
    """Return row-level Error counts and reviewed/not-verified flags.

    All members of within-upload duplicate groups enter Error. Missing approved
    registers never silently produce a database-uniqueness PASS. Original input
    mappings are not mutated. Approved invoice references are allowed for CNs.
    """
    items = list(rows)
    if not all(isinstance(row, Mapping) for row in items):
        raise TypeError("Credit Note rows must be mappings")
    data = [dict(row) for row in items]
    if require_credit_note_numbers and any(
        not _present(row, CREDIT_NOTE_ALIASES) for row in data
    ):
        raise ValueError("Dedicated Credit Note No column required for new Credit Notes")

    invoices = [number(_field(row, INVOICE_ALIASES)) for row in data]
    credit_notes = [number(_field(row, CREDIT_NOTE_ALIASES)) for row in data]
    replacements = [number(_field(row, REPLACEMENT_ALIASES)) for row in data]
    markers = [marker_classification(_field(row, NARRATION_ALIASES)) for row in data]
    cn_fields_present = any(_present(row, CREDIT_NOTE_ALIASES) for row in data)

    invoice_counts = Counter(x for x in invoices if x and x not in ("NA", "N/A"))
    cn_counts = Counter(x for x in credit_notes if x)
    replacement_counts = Counter(x for x in replacements if x)

    approved_cn = (None if existing_credit_note_numbers is None
                   else {number(v) for v in existing_credit_note_numbers})
    approved_invoices = (None if approved_invoice_numbers is None
                         else {number(v) for v in approved_invoice_numbers})
    existing_replacements = (
        None if existing_replacement_invoice_numbers is None
        else {number(v) for v in existing_replacement_invoice_numbers}
    )
    rows_out = []
    flags = Counter()
    for index, (src, invoice, cn_no, replacement, marker) in enumerate(
        zip(data, invoices, credit_notes, replacements, markers), start=2
    ):
        reasons = []
        if not valid_mxp_reference(invoice):
            reasons.append("INVALID_INVOICE_NO_NON_MXP")
        if invoice_counts[invoice] > 1:
            reasons.append("DUPLICATE_INVOICE_NUMBER")
        if approved_invoices is not None and invoice not in approved_invoices:
            reasons.append("INVOICE_REFERENCE_NOT_IN_APPROVED_REGISTER")
        if marker == "REVIEW":
            reasons.append("CREDIT_NOTE_WORDING_OR_DATE_REVIEW")
        elif marker != "CREDIT_NOTE":
            reasons.append("CREDIT_NOTE_MARKER_MISSING")
        if cn_fields_present:
            if require_credit_note_numbers and not cn_no:
                reasons.append("MISSING_CREDIT_NOTE_NUMBER")
            elif cn_no:
                if not valid_mxp_reference(cn_no):
                    reasons.append("INVALID_CREDIT_NOTE_NO_NON_MXP")
                if cn_counts[cn_no] > 1:
                    reasons.append("DUPLICATE_CREDIT_NOTE_NUMBER")
                if approved_cn is not None and cn_no in approved_cn:
                    reasons.append("CREDIT_NOTE_NUMBER_ALREADY_EXISTS")
        if replacement:
            if not valid_mxp_reference(replacement):
                reasons.append("INVALID_REPLACEMENT_INVOICE_NO_NON_MXP")
            if replacement_counts[replacement] > 1:
                reasons.append("DUPLICATE_REPLACEMENT_INVOICE_NO")
            if existing_replacements is not None and replacement in existing_replacements:
                reasons.append("REPLACEMENT_INVOICE_ALREADY_EXISTS")
        for reason in reasons:
            flags[reason] += 1
        rows_out.append({
            "source_row": index,
            "invoice_no": text(_field(src, INVOICE_ALIASES)),
            "credit_note_no": text(_field(src, CREDIT_NOTE_ALIASES)) if cn_fields_present else None,
            "replacement_invoice_no": text(_field(src, REPLACEMENT_ALIASES)),
            "marker": marker,
            "status": "ERROR" if reasons else "SCREENED_REFERENCE_ONLY",
            "reasons": reasons,
        })

    error_rows = sum(r["status"] == "ERROR" for r in rows_out)
    known = (approved_cn is not None and approved_invoices is not None and
             (not any(replacements) or existing_replacements is not None))
    return {
        "rows": rows_out,
        "summary": {
            "source_rows": len(data),
            "error_rows": error_rows,
            "screened_reference_only_rows": len(data) - error_rows,
            "error_flags": dict(sorted(flags.items())),
            "duplicate_invoice_groups": sum(v > 1 for v in invoice_counts.values()),
            "duplicate_credit_note_groups": sum(v > 1 for v in cn_counts.values()) if cn_fields_present else None,
            "duplicate_replacement_invoice_groups": sum(v > 1 for v in replacement_counts.values()),
            "credit_note_number_column": "PRESENT" if cn_fields_present else "NOT_PRESENT_NOT_TESTED",
            "approved_registers": "CALLER_SUPPLIED" if known else "NOT_VERIFIED",
            "financial_writes": 0,
            "production_approval": False,
        },
    }
