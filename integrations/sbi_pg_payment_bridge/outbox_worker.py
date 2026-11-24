"""Stage-only bounded PostgreSQL delivery worker with durable SQLite receipts."""
import os
import time

from sbi_pg_outbox import recover_missing_receipts, process_pending, _store
from sbi_payment_pg_bridge import persist_payment, classify_payment_rows
import payment_evidence_upload as original


def run_once():
    _store()  # checks staging identity, private ownership and durable storage
    recovered = recover_missing_receipts()
    delivered = process_pending(
        lambda payload: persist_payment(payload, original._parse),
        lambda payload: classify_payment_rows(payload, original._parse)[1],
        limit=10,
    )
    return recovered,delivered


if __name__ == '__main__':
    if os.environ.get('SBI_PG_PAYMENT_BRIDGE_ENABLED') != 'staging-only':
        raise SystemExit('Staging worker disabled')
    print('QA_OUTBOX_WORKER=STARTED',flush=True)
    while True:
        try:
            recovered,delivered = run_once()
            if recovered or delivered:
                print('QA_OUTBOX_RESTORED=%d|DELIVERED=%d' % (recovered,delivered),flush=True)
        except Exception as exc:
            print('QA_OUTBOX_WORKER_RETRY=%s' % type(exc).__name__,flush=True)
        time.sleep(15)
