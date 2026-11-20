"""D-026 synthetic-only, non-posting payment waterfall simulation.

No file, database, network, environment, CLI or upload access.
Only SYNTH-INV/SYNTH-PAY typed fabricated in-memory fixtures are accepted.
This NEVER settles a real invoice or writes a ledger. Multiple-invoice
precedence is supplied explicitly in synthetic fixtures; it is NOT an
inferred/approved production priority rule.
"""
from collections import Counter
from decimal import Decimal

from synthetic_allocation_candidates import (
    SyntheticAllocationBlocked, _invoice, _payment, _must, _net_scenarios,
)


def _prepared_invoice(raw):
    inv = _invoice(raw)
    rate = raw.get("approved_tds_rate")
    _must(type(rate) is int and rate in (0, 1, 2, 3),
          "EXPLICIT_SYNTHETIC_TDS_RATE_REQUIRED")
    priority = raw.get("simulation_priority")
    _must(type(priority) is int and 1 <= priority <= 999999,
          "EXPLICIT_SYNTHETIC_ORDER_REQUIRED")
    inv["net_due"] = _net_scenarios(inv)[rate]
    _must(inv["net_due"] > Decimal("0"), "POSITIVE_SYNTHETIC_DUE_REQUIRED")
    inv["simulation_priority"] = priority
    inv["approved_tds_rate"] = rate
    return inv


def _prepared_payment(raw):
    pay = _payment(raw)
    allow_fifo = raw.get("allow_synthetic_fifo")
    _must(type(allow_fifo) is bool, "EXPLICIT_FIFO_MARKER_REQUIRED")
    pay["allow_synthetic_fifo"] = allow_fifo
    return pay


def _eligibility_reason(inv, payment):
    """Only compare fabricated invoice and payment data."""
    if inv["sol"] != payment["sol"]:
        return "CROSS_SOL_FORBIDDEN"
    if inv["sbisa"] != payment["sbisa"]:
        return "SBISA_IDENTITY_CONFLICT"
    if inv["protected"]:
        return "PROTECTED_INVOICE"
    if inv["credit_note"]:
        return "CREDIT_NOTE_REVIEW"
    age = (payment["date"] - inv["date"]).days
    if age < 0 or age > 180:
        return "PAYMENT_OUTSIDE_180_DAYS"
    if payment["narration_months"] and not (
            inv["months"] <= payment["narration_months"]):
        return "CONTRADICTORY_SERVICE_PERIOD"
    return None


def simulate_synthetic_waterfall(invoices, payments, *, synthetic_mode=False):
    """Simulate full, partial and split receipts with NO ledger write.

    Uses an *explicit supplied synthetic order* for multi-invoice splits.
    Payment proposals are committed only to a local temporary balance after
    an entire payment can be placed; overpayment/multiple candidates are held.
    No preexisting allocations or prior financial records are read.
    """
    _must(synthetic_mode is True, "SYNTHETIC_MODE_ONLY")
    _must(isinstance(invoices, list) and isinstance(payments, list),
          "SYNTHETIC_LISTS_REQUIRED")
    prepared_invoices = [_prepared_invoice(row) for row in invoices]
    prepared_payments = [_prepared_payment(row) for row in payments]
    invoice_counts = Counter(x["invoice_no"] for x in prepared_invoices)
    payment_counts = Counter(x["payment_id"] for x in prepared_payments)
    unique_invoices = {
        x["invoice_no"]: x for x in prepared_invoices
        if invoice_counts[x["invoice_no"]] == 1
    }
    balances = {key: inv["net_due"]
                for key, inv in unique_invoices.items()}
    proposals = []
    holds = []

    def hold(pay, reason):
        holds.append({"payment_id": pay["payment_id"], "reason": reason})

    # Bank date order is only for synthetic reproducibility; not an approved
    # historical or production waterfall-priority decision.
    for payment in sorted(prepared_payments,
                          key=lambda x: (x["date"], x["payment_id"])):
        if payment_counts[payment["payment_id"]] != 1:
            hold(payment, "DUPLICATE_PAYMENT_ID")
            continue

        explicit = payment["invoice_ref"] is not None
        if explicit:
            key = payment["invoice_ref"]
            if invoice_counts[key] > 1:
                hold(payment, "DUPLICATE_INVOICE_REFERENCE")
                continue
            if key not in unique_invoices:
                hold(payment, "INVOICE_REFERENCE_NOT_FOUND")
                continue
            chosen = [unique_invoices[key]]
        else:
            chosen = [
                inv for inv in unique_invoices.values()
                if inv["sol"] == payment["sol"]
            ]
            if not chosen:
                hold(payment, "NO_SAME_SOL_INVOICE")
                continue

        eligible = []
        reasons = set()
        for inv in chosen:
            reason = _eligibility_reason(inv, payment)
            if reason:
                reasons.add(reason)
                continue
            if balances[inv["invoice_no"]] <= 0:
                reasons.add("INVOICE_ALREADY_SATISFIED_IN_SIMULATION")
                continue
            eligible.append(inv)
        if not eligible:
            hold(payment, sorted(reasons)[0] if reasons
                 else "NO_ELIGIBLE_INVOICE")
            continue

        if not explicit and len(eligible) > 1:
            if not payment["allow_synthetic_fifo"]:
                hold(payment, "MULTIPLE_SAME_SOL_INVOICES_REVIEW")
                continue
            if not payment["narration_months"]:
                hold(payment, "MULTI_INVOICE_REQUIRES_PERIOD_EVIDENCE")
                continue
            ranks = [inv["simulation_priority"] for inv in eligible]
            if len(ranks) != len(set(ranks)):
                hold(payment, "AMBIGUOUS_SYNTHETIC_PRIORITY")
                continue
            eligible.sort(key=lambda x: x["simulation_priority"])
        elif not explicit and not payment["allow_synthetic_fifo"]:
            # Require explicit synthetic opt-in even with a single invoice
            # when the payment lacks an exact invoice reference.
            hold(payment, "UNREFERENCED_PAYMENT_NEEDS_REVIEW")
            continue

        available = sum((balances[x["invoice_no"]] for x in eligible),
                        Decimal("0"))
        if payment["credit"] > available:
            hold(payment, "OVERPAYMENT_OR_UNALLOCATABLE_REMAINDER")
            continue

        pending = []
        unused = payment["credit"]
        for inv in eligible:
            if unused == 0:
                break
            value = min(unused, balances[inv["invoice_no"]])
            if value <= 0:
                continue
            pending.append((inv["invoice_no"], value))
            unused -= value
        if unused != 0 or not pending:
            hold(payment, "UNALLOCATABLE_PAYMENT_REVIEW")
            continue

        # Atomic temporary balance update, never a financial database write.
        for invoice_no, value in pending:
            balances[invoice_no] -= value
            proposals.append({
                "payment_id": payment["payment_id"],
                "invoice_no": invoice_no,
                "synthetic_credit": str(value),
                "remaining_synthetic_net": str(balances[invoice_no]),
                "status": (
                    "SIMULATED_FULL" if balances[invoice_no] == 0
                    else "SIMULATED_PARTIAL"
                ),
                "decision": "SYNTHETIC_SIMULATION_NOT_APPROVED",
            })

    return {
        "status": "SYNTHETIC_WATERFALL_SIMULATION_ONLY",
        "simulated_assignments": proposals,
        "simulated_remaining_net": {
            key: str(value) for key, value in sorted(balances.items())
        },
        "holds": holds,
        "assignment_count": len(proposals),
        "hold_count": len(holds),
        "invoice_priority": "EXPLICIT_SYNTHETIC_ORDER_ONLY",
        "tds_rate": "EXPLICIT_SYNTHETIC_RATE_ONLY",
        "historical_records_processed": False,
        "original_records_modified": False,
        "payment_allocation": "SIMULATED_ONLY_NOT_EXECUTED",
        "financial_write_performed": False,
        "approved_for_settlement": False,
        "production_deployed": False,
    }
