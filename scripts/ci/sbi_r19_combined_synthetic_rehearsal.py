"""R19 combined synthetic-only rehearsal from workbook to a locked Excel review.

This script is NOT a Master v2.51 / Matrix v2.39 engine, approved Excel writer,
invoice allocation, database connector, or real-bank input processor. All source
rows MUST have synthetic fixture IDs and synthetic branch identities.
All output model statuses are SUSPENSE; no results are persisted.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import re

from openpyxl import Workbook, load_workbook

from sbi_r15_financial_source_preflight import inspect_original_workbook, _classify_credit
from sbi_r16_master_identity_shadow import shadow_identity_preflight
from sbi_r17_synthetic_financial_shadow import (
    SyntheticInvoice, SyntheticPayment, SyntheticReservation,
    review_one_payment_invoice, audit_shadow_reservations,
)
from sbi_r18_output_parity_gate import (
    PAYMENT_MODEL, INVOICE_MODEL, audit_candidate_source,
    verify_xlsx_output_structure, verify_53_header_contract,
)

INVOICE_ID = re.compile(r"SYN-MXP-[0-9]{3,6}\Z")
PAYMENT_ID = re.compile(r"SYN-PAY-[0-9]{3,6}\Z")
ANY_REFERENCE = re.compile(r"(?<![A-Z0-9])SYN-MXP-[0-9]{3,6}(?![A-Z0-9])")
PERIOD = re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")
EXPECTED_PAYMENT_FIELDS = {
    1: "Description", 2: "Posting Date", 3: "Service Period",
    4: "Synthetic Row ID", 6: "Branch Code", 7: "Client Name",
    8: "Debit", 9: "Credit", 10: "Balance", 11: "Record For Me",
}
EXPECTED_INVOICE_FIELDS = {
    5: "Month", 6: "Invoice Date", 7: "Branch Code", 8: "Client Name",
    13: "Invoice No", 14: "Taxable Amount", 15: "CGST", 16: "SGST",
    17: "Total Bill Amount",
}
SOURCE_GATE_NAMES = (
    "R15_ORIGINAL_SOURCE_PREFLIGHT",
    "R16_SOL_MASTER_IDENTITY",
    "R17_REVIEW_MATH_AND_GLOBAL_CAPACITY",
    "R18_EXCEL_AND_REPORT_SCHEMA",
)
PENDING_GATES = (
    "R14_REAL_FIREBASE_TO_FLASK_SESSION_NOT_VERIFIED",
    "MASTER_V251_MATRIX_V239_EXECUTABLE_NOT_CERTIFIED",
    "FRESH_PRIVATE_BANK_SOURCE_NOT_ATTESTED",
    "LATEST_OFFICIALLY_APPROVED_SOL_MASTER_NOT_ATTESTED",
    "INDEPENDENT_FULL_RULE_AND_LEDGER_ORACLE_NOT_RUN",
    "REAL_V218_FINANCIAL_WRITER_NOT_INTEGRATED",
    "FINANCIAL_AMOUNT_AND_REPORT_PARITY_NOT_VERIFIED",
    "POSTGRESQL_READONLY_SNAPSHOT_ROLLBACK_NOT_VERIFIED",
    "FINANCE_SECURITY_RELEASE_NOT_AUTHORIZED",
)


class R19CombinedGateError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def refuse(code):
    raise R19CombinedGateError(code)


def workbook_bytes(workbook):
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _strict_sol(value):
    return isinstance(value, str) and bool(re.fullmatch("[0-9]{1,12}", value))


def _literal_date(value):
    if type(value) is date:
        return value
    if type(value) is datetime:
        return value.date()
    refuse("SYNTHETIC_SOURCE_DATE_REQUIRED")


def _literal_period(value):
    if not isinstance(value, str) or not PERIOD.fullmatch(value):
        refuse("SYNTHETIC_SOURCE_PERIOD_REQUIRED")
    return value


def _strict_synthetic_inputs(source_bytes, master_bytes):
    # NOTE: This is intentionally restrictive: it cannot be pointed at real SBI
    # files as a workaround to the missing FFI-001 provenance and Finance release.
    a = load_workbook(io.BytesIO(source_bytes), read_only=True, data_only=False,
                      keep_links=False)
    b = load_workbook(io.BytesIO(master_bytes), read_only=True, data_only=False,
                      keep_links=False)
    try:
        if "PAYMNENT" not in a.sheetnames or "Invoice Details." not in a.sheetnames:
            refuse("SYNTHETIC_REQUIRED_FINANCIAL_TABS")
        if "Clean Branch Master" not in b.sheetnames:
            refuse("SYNTHETIC_MASTER_TAB_MISSING")
        p, inv, master = a["PAYMNENT"], a["Invoice Details."], b["Clean Branch Master"]
        if p.max_row > 100 or inv.max_row > 100 or master.max_row > 100:
            refuse("SYNTHETIC_FIXTURE_ROW_LIMIT")
        for col, label in EXPECTED_PAYMENT_FIELDS.items():
            if p.cell(1, col).value != label:
                refuse("SYNTHETIC_PAYMENT_HEADER_CONTRACT_MISMATCH")
        for col, label in EXPECTED_INVOICE_FIELDS.items():
            if inv.cell(1, col).value != label:
                refuse("SYNTHETIC_INVOICE_HEADER_CONTRACT_MISMATCH")
        if master.cell(1, 1).value != "Official Branch Name" or master.cell(1, 2).value != "SOL ID":
            refuse("SYNTHETIC_MASTER_HEADER_CONTRACT_MISMATCH")

        master_keys = set()
        for row in master.iter_rows(min_row=2, max_col=2):
            name, sol = row[0].value, row[1].value
            if not isinstance(name, str) or not name.startswith("SYNTHETIC ") or not _strict_sol(sol):
                refuse("NON_SYNTHETIC_MASTER_ROW_REFUSED")
            if (sol, name) in master_keys:
                refuse("DUPLICATE_SYNTHETIC_MASTER_ROW")
            master_keys.add((sol, name))

        invoices = {}
        for row in inv.iter_rows(min_row=2, max_col=34):
            key, sol, client = row[12].value, row[6].value, row[7].value
            if not isinstance(key, str) or not INVOICE_ID.fullmatch(key):
                refuse("NON_SYNTHETIC_INVOICE_ROW_REFUSED")
            if key in invoices:
                refuse("DUPLICATE_SYNTHETIC_INVOICE_ID")
            if not _strict_sol(sol) or not isinstance(client, str) or not client.startswith("SYNTHETIC "):
                refuse("NON_SYNTHETIC_INVOICE_IDENTITY_REFUSED")
            issue_date = _literal_date(row[5].value)
            period = _literal_period(row[4].value)
            if any(row[i].data_type in ("f", "e") for i in (13, 14, 15, 16)):
                refuse("SYNTHETIC_FORMULA_MONEY_UNSUPPORTED")
            taxable, cgst, sgst, gross = (
                Decimal(str(row[c].value)) for c in (13, 14, 15, 16)
            )
            if taxable + cgst + sgst != gross:
                refuse("SYNTHETIC_INVOICE_GROSS_COMPONENT_MISMATCH")
            invoices[key] = SyntheticInvoice(
                key, sol, client, str(taxable), str(gross),
                str(cgst + sgst), str(gross), issue_date, (period,), row[18].value,
            )

        payments = {}
        for row in p.iter_rows(min_row=2, max_col=12):
            key, sol, client = row[3].value, row[5].value, row[6].value
            if not isinstance(key, str) or not PAYMENT_ID.fullmatch(key):
                refuse("NON_SYNTHETIC_BANK_ROW_REFUSED")
            if key in payments:
                refuse("DUPLICATE_SYNTHETIC_BANK_ROW")
            if not _strict_sol(sol) or not isinstance(client, str) or not client.startswith("SYNTHETIC "):
                refuse("NON_SYNTHETIC_BANK_IDENTITY_REFUSED")
            if row[8].data_type in ("f", "e"):
                refuse("SYNTHETIC_FORMULA_BANK_CREDIT_UNSUPPORTED")
            _literal_date(row[1].value)
            _literal_period(row[2].value)
            desc = row[0].value
            if not isinstance(desc, str) or not desc.startswith("SYNTHETIC "):
                refuse("NON_SYNTHETIC_BANK_NARRATION_REFUSED")
            ref_ids = tuple(dict.fromkeys(ANY_REFERENCE.findall(desc)))
            payments[key] = SyntheticPayment(
                key, sol, client, str(row[8].value), _literal_date(row[1].value),
                ref_ids, (_literal_period(row[2].value),), False,
                str(row[10].value or ""),
            )
        if not payments or not invoices or not master_keys:
            refuse("EMPTY_SYNTHETIC_COMBINED_FIXTURE")
        return invoices, payments
    finally:
        a.close()
        b.close()


def build_synthetic_fixture():
    """Create purely fictitious source/master XLSX bytes, never disk files."""
    book = Workbook()
    p = book.active
    p.title = "PAYMNENT"
    inv = book.create_sheet("Invoice Details.")
    extra = book.create_sheet("SYNTHETIC AUXILIARY")
    for col, name in EXPECTED_PAYMENT_FIELDS.items():
        p.cell(1, col, name)
    # Original L header MUST remain blank. Populate L2 to prove no clobber.
    p["L2"] = "SYNTHETIC ORIGINAL PROTECTED NOTE"
    bank_rows = (
        ("SYN-PAY-001", "0001", "1160.00", "SYNTHETIC SYN-MXP-001 SEPTEMBER 2026", "", "2026-09"),
        ("SYN-PAY-002", "0001", "-5.00", "SYNTHETIC SYN-MXP-001 SEPTEMBER 2026", "", "2026-09"),
        ("SYN-PAY-003", "1", "1160.00", "SYNTHETIC SYN-MXP-001 SEPTEMBER 2026", "", "2026-09"),
        ("SYN-PAY-004", "0001", "1180.00", "SYNTHETIC SYN-MXP-002 SEPTEMBER 2026", "", "2026-09"),
        ("SYN-PAY-005", "0001", "1160.00", "SYNTHETIC SYN-MXP-001 SEPTEMBER 2026", "OK", "2026-09"),
    )
    for idx, (key, sol, credit, narration, prior, period) in enumerate(bank_rows, 2):
        for col, value in (
            (1, narration), (2, date(2026, 9, 15)), (3, period), (4, key),
            (6, sol), (7, "SYNTHETIC ALPHA"), (8, 0),
            (9, Decimal(credit)), (10, 1000), (11, prior),
        ):
            if value != "":
                p.cell(idx, col, value)
    p["J2"] = "=SUM(I2:I3)"
    p["I2"].number_format = '#,##0.00'
    for col in range(1, 35):
        inv.cell(1, col, "SYNTHETIC ORIGINAL_" + str(col))
    for col, label in EXPECTED_INVOICE_FIELDS.items():
        inv.cell(1, col, label)
    for idx, key in ((2, "SYN-MXP-001"), (3, "SYN-MXP-002")):
        for col, value in (
            (5, "2026-09"), (6, date(2026, 9, 1)),
            (7, "0001"), (8, "SYNTHETIC ALPHA"), (13, key),
            (14, 1000), (15, 90), (16, 90), (17, 1180),
        ):
            inv.cell(idx, col, value)
    inv["S3"] = 0  # Protected numeric zero is nonblank; never eligible.
    inv["AH2"] = "=SUM(N2:P2)"
    extra["A1"] = "SYNTHETIC ORIGINAL AUXILIARY"
    extra["A2"] = "=SUM(2,3)"

    master = Workbook()
    sheet = master.active
    sheet.title = "Clean Branch Master"
    sheet["A1"], sheet["B1"] = "Official Branch Name", "SOL ID"
    sheet["A2"], sheet["B2"] = "SYNTHETIC ALPHA", "0001"
    return workbook_bytes(book), workbook_bytes(master)


def synthesize_locked_output(source_bytes, reviewed_by_payment):
    """Test-only in-memory fake writer: always SUSPENSE, never production v2.18."""
    book = load_workbook(io.BytesIO(source_bytes), data_only=False)
    try:
        p, i = book["PAYMNENT"], book["Invoice Details."]
        for j, name in enumerate(PAYMENT_MODEL, start=13):
            p.cell(1, j, name)
        for j, name in enumerate(INVOICE_MODEL, start=35):
            i.cell(1, j, name)
        for row in range(2, p.max_row + 1):
            key = p.cell(row, 4).value
            if key not in reviewed_by_payment:
                refuse("SYNTHETIC_PAYMENT_DIAGNOSTIC_MISSING")
            p.cell(row, 13, "SUSPENSE")
            p.cell(row, 14, "SYNTHETIC QA HOLD — NOT AN AUTHORIZED FINANCIAL MATCH")
            p.cell(row, 17, "R19_SYNTHETIC_REVIEW_ONLY")
            p.cell(row, 21, "NOT_VERIFIED")
        for row in range(2, i.max_row + 1):
            i.cell(row, 35, "0001" if i.cell(row, 19).value is None else None)
            i.cell(row, 36, "SYNTHETIC ALPHA" if i.cell(row, 19).value is None else None)
            i.cell(row, 39, "SYNTHETIC NOT LINKED")
        return workbook_bytes(book)
    finally:
        book.close()


def combined_synthetic_run(source_bytes, master_bytes, *, expected_source_sha256,
                           expected_master_sha256, report_headers=None):
    """One deterministic in-memory run through all available R15-R18 checks.

    Has no production entrypoint and returns only aggregated evidence.
    """
    invoices, payments = _strict_synthetic_inputs(source_bytes, master_bytes)
    r15 = inspect_original_workbook(
        source_bytes, expected_sha256=expected_source_sha256
    )
    r16 = shadow_identity_preflight(
        source_bytes, master_bytes,
        expected_source_sha256=expected_source_sha256,
        expected_master_sha256=expected_master_sha256,
    )
    # A shadow financial review MUST NOT bypass the prior master gate.
    # Protected invoice rows are deliberately excluded from the eligible count.
    if (r16["master_ambiguous_sol_keys"] or r16["master_invalid_identity_rows"]
            or r16["invoice_duplicate_id_groups"]
            or r16["invoice_identity_counts"].get(
                "candidate_exact_sol_and_official_name_only", 0
            ) != 1):
        refuse("MASTER_IDENTITY_GATE_NOT_PASSED")
    r17_summary = Counter()
    reviewed = {}
    for bank in payments.values():
        if Decimal(bank.credit) <= 0:
            r17_summary["nonpositive_credit_held"] += 1
            reviewed[bank.key] = "NEGATIVE_CREDIT_HOLD"
            continue
        if len(bank.narration_refs) != 1 or bank.narration_refs[0] not in invoices:
            r17_summary["missing_or_multiple_exact_reference_held"] += 1
            reviewed[bank.key] = "REFERENCE_HOLD"
            continue
        evaluation = review_one_payment_invoice(bank, invoices[bank.narration_refs[0]])
        reviewed[bank.key] = evaluation["decision"]
        if evaluation["decision"] == "CANDIDATE_FOR_INDEPENDENT_REVIEW":
            r17_summary["candidate_for_independent_review_only"] += 1
        else:
            r17_summary["blocked_for_review"] += 1
            for code in evaluation["blocker_codes"]:
                r17_summary["hold_" + code] += 1

    # One deliberately harmless non-settling edge checks the *capacity* code path.
    example = [
        SyntheticReservation("SYN-PAY-001", "SYN-MXP-001", "100.00"),
    ]
    global_capacity = audit_shadow_reservations(
        list(payments.values()), list(invoices.values()), example
    )
    if not global_capacity["capacity_constraints_passed"]:
        refuse("SYNTHETIC_EXAMPLE_CAPACITY_CHECK_FAILED")

    locked_output = synthesize_locked_output(source_bytes, reviewed)
    r18 = verify_xlsx_output_structure(
        source_bytes, locked_output,
        expected_source_sha256=expected_source_sha256,
        expected_candidate_sha256=sha256(locked_output).hexdigest(),
    )
    path = Path(__file__).resolve().parents[2] / "backend_source" / "invoice_import_contract.json"
    approved_53_headers = json.loads(path.read_text())["headers"]
    if report_headers is None:
        report_headers = approved_53_headers
    # Never compare a caller-supplied report contract to itself.
    report_check = verify_53_header_contract(report_headers, approved_53_headers)
    candidate_gate = audit_candidate_source(None, None)

    if r16["invoice_identity_counts"].get("protected_paid_marker_s_nonblank") != 1:
        refuse("EXPECTED_PROTECTED_SYNTHETIC_INVOICE_NOT_PRESENT")
    if r17_summary["candidate_for_independent_review_only"] != 1:
        refuse("EXPECTED_EXACT_TDS_REVIEW_HYPOTHESIS_NOT_OBSERVED")
    if sum(r18["payment_status_counts_structure_only"].values()) != 4:
        refuse("EXPECTED_FOUR_POSITIVE_SYNTHETIC_BANK_ROWS")
    if r18["payment_status_counts_structure_only"] != {"SUSPENSE": 4}:
        refuse("FINANCIAL_STATUS_MUST_REMAIN_SUSPENSE")
    if report_check["header_count"] != 53:
        refuse("FIFTY_THREE_REPORT_HEADERS_NOT_PRESERVED")

    return {
        "stage": "R19_SYNTHETIC_FULL_CHAIN_REHEARSAL_ONLY",
        "completed_offline_stages": SOURCE_GATE_NAMES,
        "source_sha256": r15["source_sha256"],
        "master_sha256": r16["master_sha256"],
        "mock_writer_output_sha256": sha256(locked_output).hexdigest(),
        "bank_source_rows": r15["payment_rows_seen"],
        "invoice_source_rows": r15["invoice_rows_seen"],
        "protected_invoice_marker_rows": r16["invoice_identity_counts"].get(
            "protected_paid_marker_s_nonblank", 0
        ),
        "credit_evidence_counts": r15["bank_credit_evidence_counts"],
        "review_reason_counts": dict(r17_summary),
        "one_capacity_hypothesis_checked": global_capacity["hypothesis_edges_seen"] == 1,
        "output_statuses_structure_only": r18["payment_status_counts_structure_only"],
        "output_original_cells_unchanged": r18["original_cells_formulas_number_formats_preserved"],
        "output_model_payment_columns": r18["model_payment_columns"],
        "output_model_invoice_columns": r18["model_invoice_columns"],
        "report_53_header_order_preserved": report_check["duplicate_header_positions_preserved"],
        "v251_candidate_gate": candidate_gate["gate"],
        "pending_real_release_gates": PENDING_GATES,
        "engine_v251_certified": False,
        "financial_apply_locked": True,
        "financial_statuses_approved": 0,
        "real_financial_allocations": 0,
        "financial_database_connected": False,
        "real_firebase_app_session_tested": False,
        "production_excel_writer_connected": False,
        "production_release_ready": False,
    }


def run_default_fixture():
    source, master = build_synthetic_fixture()
    return combined_synthetic_run(
        source, master,
        expected_source_sha256=sha256(source).hexdigest(),
        expected_master_sha256=sha256(master).hexdigest(),
    )


if __name__ == "__main__":
    print(json.dumps(run_default_fixture(), indent=2, sort_keys=True))
