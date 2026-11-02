"""Category-wise reconciliation change counts."""

from collections import Counter

PAYMENT_CATEGORIES = ("unpaid", "ok", "error-value")
ALL_CATEGORIES = PAYMENT_CATEGORIES + ("balance-review",)

CHANGE_TAGS = (
    "NEW", "UNCHANGED", "PAYMENT_ADDED",
    "PAYMENT_CHANGED", "PAYMENT_CLEARED_REVIEW",
    "CONFLICT",
)


def build_change_breakdown(report):
    details = report["details"]
    breakdown = {
        name: {tag: 0 for tag in CHANGE_TAGS}
        for name in ALL_CATEGORIES
    }
    unclassified = Counter()

    for item in details:
        tag = item["tag"]
        if tag not in CHANGE_TAGS:
            raise ValueError("Unknown change tag")

        category = item.get("previous_report")

        if category in PAYMENT_CATEGORIES:
            breakdown[category][tag] += 1
        else:
            unclassified[tag] += 1

        if item.get("balance_review") is True:
            breakdown["balance-review"][tag] += 1

    totals = Counter(item["tag"] for item in details)

    if sum(totals.values()) != report["summary"]["total"]:
        raise ValueError("Invoice change totals mismatch")

    return {
        "total_invoices": len(details),
        "change_counts": {
            tag: totals[tag] for tag in CHANGE_TAGS
        },
        "report_breakdown": breakdown,
        "unclassified": {
            tag: unclassified[tag] for tag in CHANGE_TAGS
        },
    }
