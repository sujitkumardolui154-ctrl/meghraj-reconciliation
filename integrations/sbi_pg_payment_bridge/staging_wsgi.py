"""Stage-only entrypoint. Do not wire this module into production Gunicorn."""
import os
from pathlib import Path

if os.getenv('SBI_PG_PAYMENT_BRIDGE_ENABLED') != 'staging-only':
    raise RuntimeError('Staging-only bridge is not enabled')
folder = Path(os.environ.get('SBI_PAYMENT_EVIDENCE_DIR', '/tmp/sbi-stage-receipts'))
if not folder.is_absolute() or folder.is_symlink():
    raise RuntimeError('Invalid QA receipt folder')
folder.mkdir(mode=0o700, parents=True, exist_ok=True)
folder.chmod(0o700)
os.environ['SBI_PAYMENT_EVIDENCE_DIR'] = str(folder)
from app import app
from sbi_payment_pg_bridge import attach
attach(app)
