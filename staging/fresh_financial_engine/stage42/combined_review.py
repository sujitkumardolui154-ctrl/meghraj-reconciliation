"""NEW engine 21 11 2026 — Stage 4.2/4.5 combined synthetic integration.

Offline review contract ONLY. All files must be fabricated SYNTHETIC_ workbooks.
Uses Stage 4's signed internal-gateway intake and candidate *review* ledger,
then Stage 4.1's repaired v2.18 SUSPENSE-only writer. No financial allocator,
reservation, settlement, history scan, live bank authentication or AWS API.

The source layout MUST match the pinned v2.18 nine-sheet manifest. Newer
SBI invoice layouts are intentionally refused until approved mapping is built.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import tempfile
from typing import Any

from stage4_ledger import (
    NewOnlyCandidateLedger, Principal, Stage4Policy, verify_attestation,
    bank_fields, invoice_fields, paise,
)
from v218_writer import (
    _read_snap, _check_input, OutputReviewBlocked,
    write_synthetic_v218_review,
)

MANIFEST = Path(__file__).resolve().parent / 'references' / 'V218_OUTPUT_HEADER_LOCK_MANIFEST.json'

class CombinedReviewBlocked(ValueError):
    pass


def guard(ok: bool, reason: str) -> None:
    if not ok:
        raise CombinedReviewBlocked(reason)


def scalar(cells: dict, row: int, col: int, *, allowed: tuple[str, ...] = ('text',)) -> str:
    value = cells.get((row, col))
    guard(value is not None and value[0] in allowed and value[2] is None and value[1] is not None,
          f'EXACT_SOURCE_CELL_REQUIRED_{row}_{col}')
    return str(value[1])


def source_amount(cells: dict, row: int, col: int) -> int:
    cell = cells.get((row, col))
    guard(cell is not None and cell[0] in ('number', 'text') and cell[2] is None,
          f'NUMERIC_SOURCE_AMOUNT_REQUIRED_{row}_{col}')
    try:
        raw = Decimal(str(cell[1]))
        value = raw * 100
    except Exception as exc:
        raise CombinedReviewBlocked(f'NUMERIC_SOURCE_AMOUNT_REQUIRED_{row}_{col}') from exc
    guard(value.is_finite() and raw >= 0 and value == value.to_integral_value(),
          'SOURCE_AMOUNT_NOT_EXACT_PAISE')
    return int(value)


def validate_source_contract(src: Path, bank: dict, invoice: dict) -> None:
    """Independently compare signed NEW_ONLY claims to exact synthetic source cells.

    No date serial guessing, no fuzzy aliasing or automatic v2.18/newer conversion.
    This integration deliberately requires ISO text dates and YYYY-MM period.
    """
    guard(src.name.startswith('SYNTHETIC_') and src.suffix == '.xlsx',
          'SYNTHETIC_SOURCE_ONLY')
    guard(src.is_file(), 'SYNTHETIC_SOURCE_NOT_FOUND')
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    guard(bank['source_sha256'] == digest and invoice['source_sha256'] == digest,
          'SIGNED_SOURCE_FILE_SHA_MISMATCH')
    try:
        snapshot = _read_snap(src)
        manifest = json.loads(MANIFEST.read_text('utf8'))
        _check_input(snapshot, manifest)
    except (OutputReviewBlocked, KeyError, ValueError) as exc:
        raise CombinedReviewBlocked('UNAPPROVED_V218_SOURCE_LAYOUT') from exc

    sheets = snapshot[1]
    pay = sheets['PAYMNENT']; inv = sheets['Invoice Details.']
    p = bank['source_row']; i = invoice['source_row']
    guard(type(p) is int and type(i) is int and 2 <= p <= 1000 and 2 <= i <= 1000,
          'SIGNED_SOURCE_ROW_INVALID')
    # Current combined QA explicitly tests ONE new receipt and ONE new invoice.
    # Never silently produce default statuses for unknown legacy rows.
    pay_rows = {row for row,col in pay if row > 1 and col <= 12}
    invoice_rows = {row for row,col in inv if row > 1 and col <= 34}
    guard(pay_rows == {p} and invoice_rows == {i}, 'SINGLE_SYNTHETIC_PAIR_ONLY')

    # Payment E description, F SOL, I original incoming bank Credit; C date.
    guard(scalar(pay,p,5) == bank['description'], 'BANK_NARRATION_SOURCE_CONFLICT')
    guard(scalar(pay,p,6) == bank['sol_id'], 'BANK_SOL_SOURCE_CONFLICT')
    guard(scalar(pay,p,3) == bank['bank_date'], 'BANK_DATE_SOURCE_CONFLICT')
    guard(source_amount(pay,p,9) == paise(bank['credit_amount']),
          'BANK_CREDIT_I_SOURCE_CONFLICT')

    # PINNED v2.18 invoice: E month, F invoice date, G SOL, H client,
    # J invoice number, K taxable, L CGST, M SGST, N gross, S paid marker.
    guard(scalar(inv,i,5) == invoice['service_month'], 'INVOICE_PERIOD_SOURCE_CONFLICT')
    guard(scalar(inv,i,6) == invoice['invoice_date'], 'INVOICE_DATE_SOURCE_CONFLICT')
    guard(scalar(inv,i,7) == invoice['sol_id'], 'INVOICE_SOL_SOURCE_CONFLICT')
    guard(scalar(inv,i,8) == invoice['client_name'], 'INVOICE_CLIENT_SOURCE_CONFLICT')
    guard(scalar(inv,i,10) == invoice['invoice_no'], 'INVOICE_REFERENCE_SOURCE_CONFLICT')
    for col,field in ((11,'taxable'),(12,'cgst'),(13,'sgst'),(14,'gross')):
        guard(source_amount(inv,i,col) == paise(invoice[field],nonzero=field in ('taxable','gross')),
              f'INVOICE_{field.upper()}_SOURCE_CONFLICT')
    paid=inv.get((i,19))
    guard(paid is None or (paid[1] is None and paid[2] is None),
          'ORIGINAL_INVOICE_PAID_MARKER_PRESENT')


def run_combined_review(*, source_xlsx: str|Path, output_xlsx: str|Path,
                        payment_row: dict, bank_evidence: dict, bank_tag: str,
                        invoice_evidence: dict, invoice_tag: str,
                        policy: Stage4Policy, uploader: Principal,
                        reviewer: Principal) -> dict[str, Any]:
    """One fabricated E2E review, no auto-allocation and no permanent DB writes."""
    src=Path(source_xlsx);dst=Path(output_xlsx)
    guard(dst.name.startswith('SYNTHETIC_') and dst.suffix == '.xlsx',
          'SYNTHETIC_OUTPUT_ONLY')
    guard(not dst.exists(), 'OUTPUT_ALREADY_EXISTS')
    guard(type(policy) is Stage4Policy and policy.finance_apply_enabled is False,
          'FINANCIAL_APPLY_LOCK_REQUIRED')
    guard(type(uploader) is Principal and uploader.role == 'INTAKE' and
          type(reviewer) is Principal and reviewer.role == 'REVIEWER' and
          uploader.uid != reviewer.uid,'DISTINCT_TEST_ROLES_REQUIRED')
    # Verify attestation signatures and *all* fields before database mutation.
    signed_bank,_ = verify_attestation(bank_evidence,bank_tag,policy,'bank')
    signed_invoice,_ = verify_attestation(invoice_evidence,invoice_tag,policy,'invoice')
    bank_fields(signed_bank,policy)
    invoice_fields(signed_invoice,policy)
    guard(bank_evidence['invoice_reference'] == invoice_evidence['invoice_no'],
          'CROSS_SOURCE_INVOICE_REFERENCE_CONFLICT')
    guard(bank_evidence['sol_id'] == invoice_evidence['sol_id'] and
          bank_evidence['client_name'] == invoice_evidence['client_name'] and
          bank_evidence['service_month'] == invoice_evidence['service_month'],
          'CROSS_SOURCE_SOL_CLIENT_PERIOD_CONFLICT')
    bd=date.fromisoformat(bank_evidence['bank_date']);idate=date.fromisoformat(invoice_evidence['invoice_date'])
    guard(0 <= (bd-idate).days <= 180, 'DATE_CHRONOLOGY_OR_180D_CONFLICT')
    validate_source_contract(src,bank_evidence,invoice_evidence)

    # A temporary local Stage 4 SQLite ledger exercises persistent SQL txns,
    # then is destroyed at end. No finance DB credentials/paths are accepted.
    with tempfile.TemporaryDirectory(prefix='SBI_SYNTH_COMBINED_') as tmp:
        with NewOnlyCandidateLedger(str(Path(tmp)/'candidate.sqlite3'),policy) as ledger:
            ledger.stage_uploaded_bank(payment_row,bank_evidence,bank_tag,actor=uploader)
            ledger.record_invoice(invoice_evidence,invoice_tag,actor=uploader)
            ledger.review_bank(bank_evidence['payment_reference'],actor=reviewer)
            status=ledger.status()
            guard(status['counts']['reservations'] == 0 and
                  status['counts']['receipts'] == 1 and status['counts']['invoices'] == 1,
                  'UNEXPECTED_LEDGER_RESERVATION')

            p=bank_evidence['source_row'];i=invoice_evidence['source_row']
            models={p:[
                'SUSPENSE','SIGNED INTERNAL GATEWAY REVIEW ONLY; BANK NOT INDEPENDENTLY VERIFIED',
                invoice_evidence['invoice_no'],i,'SOURCE_ONLY_REVIEW',None,
                bank_evidence['credit_amount'],None,bank_evidence['service_month'],
                bank_evidence['sol_id'],bank_evidence['client_name'],
            ]}
            inv_models={i:[invoice_evidence['sol_id'],invoice_evidence['client_name'],
                            p,bank_evidence['credit_amount'],'SIGNED CANDIDATE; NOT SETTLED']}
            outcome=write_synthetic_v218_review(src,dst,models,inv_models,manifest_path=MANIFEST)
            guard(outcome['financial_writes'] is False and
                  outcome['source_cells_preserved'] is True,
                  'WRITER_INTEGRITY_FAILURE')
            guard(ledger.status()['counts']['reservations'] == 0,
                  'LEDGER_MUTATION_BY_WRITER')

    return {
        'engine':'NEW engine 21 11 2026',
        'combined_stage':'STAGE_4_2_TO_4_5_SOURCE_REVIEW_ONLY',
        'status':'SYNTHETIC_COMBINED_QA_PASS_NOT_FINANCE_CERTIFICATION',
        'source_layout':'PINNED_LEGACY_V218_ONLY',
        'payment_model_status':'SUSPENSE',
        'bank_origin_independently_authenticated':False,
        'firebase_roles_authenticated':False,
        'financial_allocations':0,
        'candidate_reservations':0,
        'original_source_cells_preserved':True,
        'ledger_persisted_after_run':False,
        'financial_writes':False,
        'historical_records_processed':False,
        'production_apply_enabled':False,
        'output_path':str(dst),
    }
