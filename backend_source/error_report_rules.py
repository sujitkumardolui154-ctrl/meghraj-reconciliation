"""Issue #76: read-only, separate SBI error report; no financial mutations.

The approved 53-column input is positional and immutable. This module does not
connect to databases, approve evidence, or change reconciliation outcomes.
"""
from collections import Counter, defaultdict
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import re

from invoice_source_schema import HEADERS_53

RULES = {
    "ERR-01_GROSS_MISMATCH": "HIGH",
    "ERR-02_INVALID_FINANCIAL_VALUE": "HIGH",
    "ERR-03_DUPLICATE_INVOICE": "HIGH",
    "ERR-04_INVALID_INVOICE_NUMBER": "HIGH",
    "ERR-05_BRANCH_CODE_CONFLICT": "MEDIUM",
    "ERR-06_SOL_MISMATCH": "HIGH",
    "ERR-07_MISSING_MODEL_SOL": "MEDIUM",
    "ERR-08_PAYMENT_EVIDENCE_MISSING": "CRITICAL",
    "ERR-09_STATUS_EVIDENCE_CONFLICT": "CRITICAL",
    "ERR-10_MASTER_REPORT_PARITY": "CRITICAL",
    "ERR-11_CREDIT_NOTE_PARITY": "HIGH",
    "ERR-12_BACKUP_ROLLBACK": "CRITICAL",
}
REPORT_COLUMNS = (
    "Run ID", "Source SHA256", "Source Row", "Invoice No", "Branch Code",
    "Model SOL ID", "Error Code", "Severity", "Detection Status", "Field",
    "Source Value", "Expected Value", "Difference", "Explanation",
    "Review Decision", "Rule Version",
)
PLACEHOLDERS = {"", "NA", "N/A", "NULL", "NONE"}
AMOUNT_COLUMNS = ((13, "Taxable Amount"), (14, "CGST"),
                  (15, "SGST"), (16, "Total Bill Amount"))
COMPARE_AMOUNTS = (13, 14, 15, 16, 17, 20)
RULE_VERSION = "SBI_ERR_V1"


def _number(text):
    value = str(text).strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value):
        raise ValueError("Invalid decimal")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("Non-finite decimal")
    return result


def _code(value):
    # Never strip leading zeros from bank SOL codes or invoice numbers.
    return str(value).strip().casefold()


def _is_missing(invoice):
    return str(invoice).strip().upper() in PLACEHOLDERS


def _safe_cell(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\n", "\r")):
        return "'" + text
    return text


def render_error_report_csv(findings):
    """Independent report schema; formula injection protected."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for finding in findings:
        writer.writerow({col: _safe_cell(finding.get(col, "")) for col in REPORT_COLUMNS})
    return output.getvalue()


def summarize(findings):
    """A finding count is NOT the unique-invoice count."""
    return {
        "findings": len(findings),
        "by_rule": dict(sorted(Counter(f["Error Code"] for f in findings).items())),
        "by_severity": dict(sorted(Counter(f["Severity"] for f in findings).items())),
        "source_rows_flagged": len({f["Source Row"] for f in findings if f["Source Row"]}),
        "unresolved": sum(f["Review Decision"] == "PENDING_REVIEW" for f in findings),
    }


def audit_error_report(
    headers, rows, *, source_sha256, run_id="SYNTHETIC",
    report_category=None, bank_evidence=None, approved_master=None,
    credit_note_report=None, backup_proof=None,
):
    """Return independent findings; never mutate source, payments or statuses.

    Optional independent evidence is only compared mechanically; a caller must
    separately verify ownership, source fingerprints and reviewer approval.
    Missing evidence produces dataset-level BLOCKED/NOT_VERIFIABLE, not thousands
    of unsupported invoice accusations.
    """
    if tuple(headers) != tuple(HEADERS_53):
        raise ValueError("Approved 53-column header and positions must remain unchanged")
    if not re.fullmatch(r"[0-9a-f]{64}", str(source_sha256)):
        raise ValueError("Source SHA256 must be supplied")
    source_rows = []
    for raw in rows:
        if isinstance(raw, Mapping) or isinstance(raw, (str, bytes)):
            raise ValueError("Positional source rows required: duplicate headers exist")
        item = tuple(raw)
        if len(item) != 53 or any(not isinstance(cell, str) for cell in item):
            raise ValueError("Source row width/type invalid")
        source_rows.append(item)

    result = []
    seen = set()

    def flag(rule, number=0, *, field="", source="", expected="", delta="",
             note="", state="FLAGGED"):
        row = source_rows[number - 2] if number else None
        key = (rule, number)
        if key in seen:
            return
        seen.add(key)
        result.append({
            "Run ID": run_id,
            "Source SHA256": source_sha256,
            "Source Row": number or "",
            "Invoice No": row[12] if row else "",
            "Branch Code": row[6] if row else "",
            "Model SOL ID": row[8] if row else "",
            "Error Code": rule,
            "Severity": RULES[rule],
            "Detection Status": state,
            "Field": field,
            "Source Value": str(source),
            "Expected Value": str(expected),
            "Difference": str(delta),
            "Explanation": note,
            "Review Decision": "PENDING_REVIEW",
            "Rule Version": RULE_VERSION,
        })

    groups = defaultdict(list)
    for line, row in enumerate(source_rows, start=2):
        invoice = row[12].strip()
        if _is_missing(invoice):
            flag("ERR-04_INVALID_INVOICE_NUMBER", line, field="Invoice No",
                 source=invoice, note="Missing or placeholder invoice ID")
        else:
            groups[invoice].append(line)

        nums = {}
        for col, label in AMOUNT_COLUMNS:
            try:
                nums[col] = _number(row[col])
            except ValueError:
                flag("ERR-02_INVALID_FINANCIAL_VALUE", line, field=label,
                     source=row[col], note="Required financial value is not numeric")
        if len(nums) == 4:
            calculated = nums[13] + nums[14] + nums[15]
            difference = nums[16] - calculated
            if abs(difference) > Decimal("0.01"):
                flag("ERR-01_GROSS_MISMATCH", line, field="Total Bill Amount",
                     source=row[16], expected=str(calculated), delta=str(difference),
                     note="Bill total differs from taxable + CGST + SGST")

        if row[6].strip() and row[10].strip() and _code(row[6]) != _code(row[10]):
            flag("ERR-05_BRANCH_CODE_CONFLICT", line, field="Branch Code G vs K",
                 source=row[6], expected=row[10], note="Existing code columns disagree")
        if not row[8].strip() or row[8].strip().upper() in PLACEHOLDERS:
            flag("ERR-07_MISSING_MODEL_SOL", line, field="Model SOL ID",
                 note="SOL mapping absent; no automatic inference")
        elif row[6].strip() and _code(row[6]) != _code(row[8]):
            flag("ERR-06_SOL_MISMATCH", line, field="Branch Code G vs Model SOL ID",
                 source=row[6], expected=row[8],
                 note="Source branch code disagrees with model SOL")

        status = row[37].strip().upper()
        category = str(report_category or "").strip().lower()
        if (category == "ok" and
            ("SKIPPED" in status or "REVIEW" in status or "SUSPENSE" in status)):
            flag("ERR-09_STATUS_EVIDENCE_CONFLICT", line,
                 field="Model Reconciliation Status",
                 source=row[37], expected="Independently verified OK",
                 note="Report category and source reconciliation status need review")

    for invoice, positions in groups.items():
        if len(positions) > 1:
            for position in positions:
                flag("ERR-03_DUPLICATE_INVOICE", position,
                     field="Invoice No", source=invoice,
                     expected="Unique validated invoice reference",
                     note="Repeated non-placeholder invoice key; no auto resolution")

    if bank_evidence is None:
        flag("ERR-08_PAYMENT_EVIDENCE_MISSING", field="Bank payment ledger",
             note="Independent payment ledger absent; individual payments not judged",
             state="NOT_VERIFIABLE")
    else:
        # Invoice-number-only lookups cannot prove a bank allocation. Matching
        # must begin with SOL, bank credit I, amount/TDS, period and eligibility;
        # duplicates require original-row identity and a globally unique ledger.
        # This standalone flagger has no independently authenticated ledger
        # adapter, so supplied mappings remain unverified at dataset scope.
        flag("ERR-08_PAYMENT_EVIDENCE_MISSING",
             field="Independent bank allocation verification",
             note="Caller-supplied bank evidence is not independently authenticated "
                  "or matched by SOL, amount, period, eligibility and unique "
                  "source row; no invoice-level payment conclusion",
             state="NOT_VERIFIABLE")

    if approved_master is None:
        flag("ERR-10_MASTER_REPORT_PARITY", field="Approved original invoice source",
             note="Approved original 53-column master and independent digest unavailable",
             state="BLOCKED")
    else:
        if not isinstance(approved_master, Mapping) or tuple(approved_master.get("headers", ())) != tuple(HEADERS_53):
            flag("ERR-10_MASTER_REPORT_PARITY", field="Master headers",
                 note="Approved master headers missing or changed", state="BLOCKED")
        else:
            master_groups = defaultdict(list)
            for mrow in approved_master.get("rows", ()):
                mrow = tuple(mrow)
                if len(mrow) != 53:
                    raise ValueError("Approved master row width mismatch")
                if not _is_missing(mrow[12]):
                    master_groups[mrow[12].strip()].append(mrow)
            for line, row in enumerate(source_rows, start=2):
                if _is_missing(row[12]):
                    continue
                matched = master_groups.get(row[12].strip(), [])
                if len(matched) != 1 or any(row[i] != matched[0][i] for i in COMPARE_AMOUNTS):
                    flag("ERR-10_MASTER_REPORT_PARITY", line, field="Invoice source values",
                         note="Master invoice match missing, ambiguous or financial value differs",
                         state="FLAGGED")

    if credit_note_report is None:
        flag("ERR-11_CREDIT_NOTE_PARITY", field="Approved 18-column Credit Note",
             note="Credit Note report and independently approved hash unavailable",
             state="BLOCKED")
    else:
        from credit_note_53_adapter import REPORT_HEADERS, project_credit_notes
        if (not isinstance(credit_note_report, Mapping)
            or tuple(credit_note_report.get("headers", ())) != tuple(REPORT_HEADERS)):
            flag("ERR-11_CREDIT_NOTE_PARITY", field="Credit Note headers",
                 note="18-column contract missing or changed", state="BLOCKED")
        else:
            expected, _ = project_credit_notes(HEADERS_53, source_rows)
            actual = list(credit_note_report.get("rows", ()))
            if len(actual) != len(expected):
                flag("ERR-11_CREDIT_NOTE_PARITY", field="Credit Note row count",
                     source=len(actual), expected=len(expected),
                     note="Output cardinality differs", state="FLAGGED")
            for line, (want, have) in enumerate(zip(expected, actual), start=2):
                if isinstance(have, Mapping):
                    observed = tuple(have.get(k, "") for k in REPORT_HEADERS)
                else:
                    observed = tuple(have)
                if observed != tuple(want[k] for k in REPORT_HEADERS):
                    flag("ERR-11_CREDIT_NOTE_PARITY", line,
                         field="Credit Note values", note="Report projection differs")

    if backup_proof is None:
        flag("ERR-12_BACKUP_ROLLBACK", field="Backup/rollback",
             note="Authorized snapshot hash and isolated restore proof not available",
             state="NOT_VERIFIABLE")
    else:
        if not isinstance(backup_proof, Mapping):
            raise ValueError("Backup proof must be a mapping")
        snapshot = backup_proof.get("snapshot_bytes")
        restored = backup_proof.get("restored_bytes")
        expected_hash = backup_proof.get("snapshot_sha256")
        isolated = backup_proof.get("isolated") is True
        if (not isinstance(snapshot, bytes) or not isinstance(restored, bytes)
            or not isinstance(expected_hash, str)
            or not isolated
            or hashlib.sha256(snapshot).hexdigest() != expected_hash
            or hashlib.sha256(restored).hexdigest() != expected_hash):
            flag("ERR-12_BACKUP_ROLLBACK", field="Backup/rollback",
                 note="Isolated synthetic restore proof missing or hash mismatch",
                 state="FAIL")

    return result
