"""Isolated D-024 logic-only candidate probe. No live data API or upload route.

Accepts only --status or --synthetic-selftest. Never accepts a source path,
filename, URL, user-supplied invoice/payment data, or database connection.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "backend_source", ROOT / "staging" / "combined-financial-engine"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from invoice_source_schema import HEADERS_53
from reference_financial_math import combined_reference_review
from logic_only_deploy_gate import REQUIRED, check_logic_only_manifest


def safe_manifest():
    return {
        **REQUIRED,
        "existing_finance_data_paths": [],
        "historical_backfill_jobs": [],
        "financial_database_endpoints": [],
    }


def synthetic_only_check():
    policy = check_logic_only_manifest(safe_manifest())
    values = [""] * 53
    values[12] = "MXP-SYNTHETIC-TEST-ONLY"
    values[13:17] = ["100.00", "9.00", "9.00", "118.00"]
    values[20] = "0"
    invoice = {
        "source_sheet": "Invoice Details.",
        "original_headers": list(HEADERS_53),
        "original_values": values,
        "original_cell_types": ["s"] * 53,
    }
    bank = [""] * 12
    bank[8] = "117.00"
    result = combined_reference_review([invoice], [bank])
    if (result["amount_status_counts"] != {"REFERENCE_CALCULATION_ONLY": 1}
            or result["payment_allocation"] != "NOT_EXECUTED"
            or result["approved_for_settlement"] is not False
            or result["financial_write_performed"] is not False
            or result["source_independent_parity"] != "NOT_VERIFIED"):
        raise RuntimeError("SYNTHETIC_LOGIC_ONLY_QA_FAILED")
    return {
        "synthetic_logic_test": "PASS",
        "source_policy": policy["status"],
        "payment_allocation": "NOT_EXECUTED",
        "historical_record_access": "NOT_PERFORMED",
        "financial_writes": "NOT_PERFORMED",
        "production_release": "BLOCKED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="SBI logic-only isolated staging probe")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--synthetic-selftest", action="store_true")
    args = parser.parse_args(argv)
    result = synthetic_only_check() if args.synthetic_selftest else {
        "mode": "LOGIC_ONLY_ISOLATED_STAGING_CANDIDATE",
        "runtime_api": "NOT_EXPOSED",
        "canonical_allocator": "NOT_CERTIFIED",
        "historical_financial_data": "NOT_ACCESSED",
        "financial_writes": "NOT_PERFORMED",
        "production_release": "BLOCKED",
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
