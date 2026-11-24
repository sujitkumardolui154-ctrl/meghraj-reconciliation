"""R26.6: real XLSX source monetary preflight (PRIVATE / READ-ONLY API).

The module CAN inspect a real bank Excel source in a PRIVATE authorized test
environment; GitHub CI tests only use entirely SYNTHETIC tiny Excel fixtures.
The module never imports a financial engine, never writes files, never allocates
a payment, never assigns payment status, and cannot certify Master v2.51.

Excel money from source cached values is a preflight only, NOT independent
formula evaluation, a v2.18 writer, same-source settlement parity, or proof of
bank-ledger / owner-approved master correctness. No external dependencies.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from sbi_case1_payment_header_mapper import map_payment_headers, HeaderMappingRefusal

XML = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_BYTES = 30 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 140 * 1024 * 1024
ORIGINAL_INVOICE_HEADERS = {
    7: "Branch Code", 8: "Client Name", 10: "Invoice No",
    11: "Taxable Amount", 12: "CGST", 13: "SGST",
    14: "Total Bill Amount",
}
PAYMENT_HEADERS = {6: "Branch Code", 9: "Credit"}
COL_RE = re.compile(r"[A-Z]+")


class R266Refusal(ValueError):
    """Structured source-contract error without private financial values."""


def _column(ref):
    m = COL_RE.match(ref)
    if m is None:
        raise R266Refusal("INVALID_CELL_REFERENCE")
    n = 0
    for char in m.group(0):
        n = 26 * n + ord(char) - 64
    return n


def _num(raw):
    if raw is None or str(raw).strip() == "":
        return None
    try:
        x = Decimal(str(raw))
    except (ValueError, InvalidOperation):
        return None
    return x if x.is_finite() else None


def _cash(raw):
    x = _num(raw)
    return x.quantize(CENT, rounding=ROUND_HALF_UP) if x is not None else None


class _ReadOnlyXlsx:
    def __init__(self, contents):
        if not isinstance(contents, bytes) or not contents or len(contents) > MAX_BYTES:
            raise R266Refusal("XLSX_BYTES_REQUIRED_OR_TOO_LARGE")
        try:
            self.z = zipfile.ZipFile(io.BytesIO(contents), "r")
            infos = self.z.infolist()
            if sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES:
                raise R266Refusal("XLSX_UNCOMPRESSED_LIMIT")
            if self.z.testzip() is not None:
                raise R266Refusal("XLSX_CRC_FAILURE")
            wb = ET.fromstring(self.z.read("xl/workbook.xml"))
            rel = ET.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))
            targets = {x.get("Id"):x.get("Target") for x in rel}
            self.sheet_paths = {}
            for sh in wb.find(XML + "sheets"):
                target = targets[sh.get(REL + "id")]
                path = target.lstrip("/") if target.startswith("/") else "xl/" + target
                if not path.startswith("xl/worksheets/") or ".." in path:
                    raise R266Refusal("UNSUPPORTED_XLSX_WORKSHEET_TARGET")
                self.sheet_paths[sh.get("name")] = path
            self.strings = []
            if "xl/sharedStrings.xml" in self.z.namelist():
                shared = ET.fromstring(self.z.read("xl/sharedStrings.xml"))
                self.strings = [
                    "".join(x.text or "" for x in si.iter(XML + "t"))
                    for si in shared
                ]
        except (KeyError, ET.ParseError, zipfile.BadZipFile, IndexError):
            raise R266Refusal("INVALID_OR_UNSUPPORTED_XLSX_ARCHIVE")

    def rows(self, sheet, columns):
        columns = set(columns)
        if sheet not in self.sheet_paths:
            raise R266Refusal("REQUIRED_SOURCE_SHEET_MISSING")
        with self.z.open(self.sheet_paths[sheet]) as f:
            for _, row in ET.iterparse(f, events=("end",)):
                if row.tag != XML + "row":
                    continue
                values = {}
                for cell in row.findall(XML + "c"):
                    ref = cell.get("r", "")
                    column = _column(ref)
                    if column not in columns:
                        continue
                    t = cell.get("t", "n")
                    v = cell.find(XML + "v")
                    is_tag = cell.find(XML + "is")
                    formula = cell.find(XML + "f")
                    if t == "s" and v is not None:
                        value = self.strings[int(v.text)]
                    elif v is not None:
                        value = v.text
                    elif is_tag is not None:
                        value = "".join(x.text or "" for x in is_tag.iter(XML + "t"))
                    else:
                        value = None
                    values[column] = (value, t, formula is not None)
                yield int(row.get("r")), values
                row.clear()

    def close(self):
        self.z.close()


def _v(r, c):
    return r.get(c, (None, None, False))[0]


def _t(r, c):
    return r.get(c, (None, None, False))[1]


def scan_readonly_source(contents, *, expected_sha256, financial_apply="LOCKED"):
    """Totals, amount exceptions and source schema only; output has NO row values."""
    if financial_apply != "LOCKED":
        raise R266Refusal("FINANCIAL_APPLY_LOCK_REQUIRED")
    if (not isinstance(expected_sha256, str)
            or not re.fullmatch("[0-9a-f]{64}", expected_sha256)):
        raise R266Refusal("SOURCE_SHA256_REQUIRED")
    if sha256(contents if isinstance(contents, bytes) else b"").hexdigest() != expected_sha256:
        raise R266Refusal("SOURCE_SHA256_MISMATCH")

    x = _ReadOnlyXlsx(contents)
    try:
        if not {"Invoice Details.", "PAYMNENT"}.issubset(x.sheet_paths):
            raise R266Refusal("EXACT_ORIGINAL_SOURCE_SHEETS_REQUIRED")
        invoice_count = 0
        pay_count = 0
        metrics = Counter()
        gross_sum = ZERO
        taxable_sum = ZERO
        bank_positive = ZERO
        invoice_keys = Counter()
        for rowno, row in x.rows("Invoice Details.", {7,8,10,11,12,13,14,15,16,17,19}):
            if rowno == 1:
                if any(_v(row, col) != name
                       for col, name in ORIGINAL_INVOICE_HEADERS.items()):
                    raise R266Refusal("ORIGINAL_INVOICE_J_TO_N_CONTRACT_FAILED")
                continue
            invoice_count += 1
            key = str(_v(row, 10) or "").strip()
            if key:
                invoice_keys[key] += 1
            if _t(row, 7) not in ("s", "inlineStr", "str"):
                metrics["invoice_sol_not_text"] += 1
            if _v(row, 19) not in (None, ""):
                metrics["original_s_protected_nonblank"] += 1
            k, l, m, n, o, p, q = (_cash(_v(row, j))
                                    for j in (11, 12, 13, 14, 15, 16, 17))
            if k is not None: taxable_sum += k
            if n is not None:
                gross_sum += n
                if n < 0:metrics["negative_gross_credit_note_like_rows"] += 1
            if any(z is None for z in (k, l, m, n)):
                metrics["invoice_core_amount_non_numeric"] += 1
            elif abs(n-k-l-m) > CENT:
                metrics["invoice_gross_component_mismatch_over_cent"] += 1
            if None not in (n, o, p) and abs((n-o)-p) > CENT:
                metrics["invoice_receivable_after_tds_mismatch_over_cent"] += 1
            if None not in (k, o, q) and abs((k-o)-q) > CENT:
                metrics["invoice_net_taxable_after_tds_mismatch_over_cent"] += 1
            if any(_t(row,j) == "e" for j in (11,12,13,14,15,16,17)):
                metrics["invoice_cached_formula_errors"] += 1
        metrics["duplicate_invoice_groups"] = sum(1 for cnt in invoice_keys.values() if cnt > 1)
        metrics["duplicate_invoice_rows"] = sum(cnt for cnt in invoice_keys.values() if cnt > 1)
        # Payment fields follow the approved header *meaning*, not physical
        # column numbers from a historical workbook. This check is distinct
        # from historic row-count / OK status parity, which is not required.
        source_bank_header = next(x.rows("PAYMNENT", range(1,65)))[1]
        try:
            layout = map_payment_headers(tuple(
                _v(source_bank_header, col) for col in range(1,65)
            ))
        except HeaderMappingRefusal:
            raise R266Refusal("ORIGINAL_BANK_CREDIT_I_CONTRACT_FAILED")
        bank_credit_col = layout.column("Credit")
        bank_sol_col = layout.column("SOL ID")
        for rowno, row in x.rows("PAYMNENT", {bank_sol_col,bank_credit_col}):
            if rowno == 1:
                continue
            pay_count += 1
            raw = _v(row, bank_credit_col)
            if raw is None or str(raw).strip() == "":
                metrics["bank_credit_blank"] += 1
            else:
                num = _num(raw)
                if num is None:
                    metrics["bank_credit_non_numeric"] += 1
                elif num > 0:
                    metrics["bank_credit_positive"] += 1
                    bank_positive += _cash(raw)
                elif num < 0:
                    metrics["bank_credit_negative"] += 1
                else:
                    metrics["bank_credit_zero"] += 1
    finally:
        x.close()
    return {
        "stage": "R266_READONLY_REAL_OR_SYNTHETIC_INPUT_MONETARY_PREFLIGHT",
        "source_sha256": expected_sha256,
        "invoice_data_rows": invoice_count,
        "payment_data_rows": pay_count,
        "gross_cached_rounded_sum": str(gross_sum),
        "taxable_cached_rounded_sum": str(taxable_sum),
        "positive_bank_credit_rounded_sum": str(bank_positive),
        "findings": dict(metrics),
        "payment_header_normalization": layout.audit(),
        "cached_values_only_not_formula_recalculation": True,
        "historical_OK_status_copy_authorized": False,
        "reconciliation_allocation_executed": False,
        "real_financial_writer_parity_verified": False,
        "complete_master_v251_matrix_v239_certified": False,
        "financial_apply_locked": True,
        "production_database_writes": 0,
    }


def compare_readonly_snapshots(original_bytes, cleaned_bytes, *,
                               expected_original_sha256,
                               expected_cleaned_sha256, financial_apply="LOCKED"):
    """Compare populations and cash totals; NEVER assert that deletions are valid."""
    original = scan_readonly_source(
        original_bytes, expected_sha256=expected_original_sha256,
        financial_apply=financial_apply,
    )
    cleaned = scan_readonly_source(
        cleaned_bytes, expected_sha256=expected_cleaned_sha256,
        financial_apply=financial_apply,
    )
    removed_invoices = original["invoice_data_rows"] - cleaned["invoice_data_rows"]
    removed_payments = original["payment_data_rows"] - cleaned["payment_data_rows"]
    if removed_invoices < 0 or removed_payments < 0:
        raise R266Refusal("CLEANED_POPULATION_EXCEEDS_ORIGINAL")
    original_bank = Decimal(original["positive_bank_credit_rounded_sum"])
    cleaned_bank = Decimal(cleaned["positive_bank_credit_rounded_sum"])
    original_gross = Decimal(original["gross_cached_rounded_sum"])
    cleaned_gross = Decimal(cleaned["gross_cached_rounded_sum"])
    difference = cleaned_gross - original_gross
    return {
        "stage": "R266_READONLY_REAL_SOURCE_POPULATION_PARITY_GATE",
        "original_source_sha256": expected_original_sha256,
        "cleaned_source_sha256": expected_cleaned_sha256,
        "original_invoice_data_rows": original["invoice_data_rows"],
        "retained_invoice_data_rows": cleaned["invoice_data_rows"],
        "excluded_invoice_row_count": removed_invoices,
        "original_payment_data_rows": original["payment_data_rows"],
        "retained_payment_data_rows": cleaned["payment_data_rows"],
        "excluded_payment_row_count": removed_payments,
        "positive_bank_credit_total_same":
            original_bank == cleaned_bank,
        "original_positive_bank_credits": str(original_bank),
        "cleaned_positive_bank_credits": str(cleaned_bank),
        "gross_total_difference_clean_minus_original": str(difference),
        "negative_removed_invoice_net_gross_suspected": difference > ZERO,
        "original_monetary_findings": original["findings"],
        "cleaned_monetary_findings": cleaned["findings"],
        "decision": "SOURCE_REVIEW_REQUIRED_NOT_FINANCIAL_SETTLEMENT",
        "all_exclusion_owner_decisions_verified": False,
        "formula_recalculation_parity_verified": False,
        "real_v218_financial_writer_parity_verified": False,
        "real_bank_ledger_statuses_authorized": False,
        "financial_apply_locked": True,
        "production_database_writes": 0,
    }
