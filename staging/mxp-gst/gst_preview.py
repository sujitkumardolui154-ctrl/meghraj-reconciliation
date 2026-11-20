"""Read-only GST invoice preview boundary; no source, database, or settlement writes.

Only caller-provided, independently verified original-invoice evidence may make
a row READY_FOR_REVIEW. The module does not fetch or trust private source data.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import json

from matcher import resolve_name

CONTRACT = json.loads((Path(__file__).parent / "config" / "approved_alias_rules_v2_7.json").read_text(encoding="utf-8"))
HEADERS = tuple(CONTRACT["headers"])
CENT = Decimal("0.01")
SOURCE_CHECKS = (
    "invoice_number", "invoice_branch", "client_identity", "service_month",
    "invoice_date", "taxable_amount", "cgst", "sgst", "source_gross",
)


def _amount(raw):
    if isinstance(raw, bool) or raw is None:
        raise ValueError("INVALID_MONEY")
    if not isinstance(raw, (str, int, Decimal)):
        raise ValueError("INVALID_MONEY")
    try:
        val = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("INVALID_MONEY") from None
    if not val.is_finite() or val < 0 or val != val.quantize(CENT):
        raise ValueError("INVALID_MONEY")
    return val


def gst_preview(source, master, *, seen_invoices=None):
    """Return a 16-position preview and explicit verification flags.

    The input is a *single* private-source record supplied by trusted caller.
    The output is in REVIEW state, never a posting/settlement instruction.
    """
    if not isinstance(source, dict):
        raise ValueError("INVALID_SOURCE")
    if not isinstance(master, list):
        raise ValueError("PRIVATE_MASTER_REQUIRED")
    flags = []
    def flag(value):
        if value not in flags:
            flags.append(value)

    raw = str(source.get("original_branch_name") or "")
    resolved = resolve_name(raw, master)
    if resolved["status"] not in ("MATCHED", "APPROVED_SPECIFIC"):
        flag("SOL_REVIEW_REQUIRED")

    invoice = str(source.get("invoice_no") or "").strip()
    if not invoice:
        flag("INVOICE_MISSING")
    if seen_invoices is not None and invoice in seen_invoices:
        flag("DUPLICATE_INVOICE")

    evidence = source.get("independent_source_checks")
    if not isinstance(evidence, dict) or not all(evidence.get(k) is True for k in SOURCE_CHECKS):
        flag("ORIGINAL_SOURCE_VERIFICATION_INCOMPLETE")
    if not str(source.get("service_month") or "").strip():
        flag("SERVICE_MONTH_MISSING")
    if not str(source.get("invoice_date") or "").strip():
        flag("INVOICE_DATE_MISSING")

    amounts = {}
    for name in ("taxable", "cgst", "sgst", "source_gross"):
        try:
            amounts[name] = _amount(source.get(name))
        except ValueError:
            flag("INVALID_" + name.upper())
            amounts[name] = None
    if all(v is not None for v in amounts.values()):
        total = amounts["taxable"] + amounts["cgst"] + amounts["sgst"]
        if total != amounts["source_gross"]:
            flag("GROSS_MISMATCH")
    else:
        total = None

    client_class = source.get("verified_client_class")
    if client_class in ("SBI_BANK", "SBI_FUND") and evidence and evidence.get("client_identity") is True:
        gstin = CONTRACT["gstin"][client_class]
    else:
        gstin = ""
        flag("GSTIN_CLASS_REVIEW_REQUIRED")

    official = resolved.get("official_name", "")
    sol = resolved.get("sol_id", "")
    recorded_branch = str(source.get("invoice_branch") or "").strip()
    if not recorded_branch:
        flag("INVOICE_BRANCH_MISSING")
    # Do not infer invoice generation place from arbitrary branch names.
    location = str(source.get("verified_generation_location") or "").strip()
    if source.get("generation_location_verified") is not True:
        location = ""
    vals = [
        str(source.get("fy") or ""), recorded_branch, location,
        str(source.get("service_month") or ""), str(source.get("invoice_date") or ""),
        sol, official, sol, gstin, invoice,
        *(str(amounts[k]) if amounts[k] is not None else "" for k in ("taxable", "cgst", "sgst")),
        str(total) if total is not None else "",
        " | ".join(flags), raw,
    ]
    assert len(vals) == len(HEADERS) == 16
    return {"headers": list(HEADERS), "values": vals, "status": "REVIEW_REQUIRED" if flags else "READY_FOR_REVIEW", "flags": flags,
            "financial_write_performed": False, "approved_for_posting": False}
