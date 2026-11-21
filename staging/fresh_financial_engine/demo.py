"""Run fabricated SBI reconciliation demonstration; no data-file input accepted."""
import json
from sbi_engine import evaluate

fake_invoices=[
  dict(source_kind='SYNTHETIC',invoice_no='SYNTH-INV-DEMO-A',sol_id='1505',
       client_name='SYNTH BRANCH',invoice_date='2026-11-21',
       service_months=['2026-11'],taxable='100.00',cgst='9.00',sgst='9.00',
       gross='118.00',approved_tds_rate=1,sbisa=False,
       original_paid_marker=None,source_verified=True,master_verified=True,
       protected_prior=False,credit_note=False),
  dict(source_kind='SYNTHETIC',invoice_no='SYNTH-INV-DEMO-B',sol_id='1505',
       client_name='SYNTH BRANCH',invoice_date='2026-11-21',
       service_months=['2026-11'],taxable='50.00',cgst='4.50',sgst='4.50',
       gross='59.00',approved_tds_rate=1,sbisa=False,
       original_paid_marker=None,source_verified=True,master_verified=True,
       protected_prior=False,credit_note=False)
]
fake_payments=[
  dict(source_kind='SYNTHETIC',utr='SYNTH-UTR-DEMO-A',sol_id='1505',
       client_name='SYNTH BRANCH',bank_date='2026-11-22',
       description='SYNTH POSTAGE NOVEMBER 2026',credit='50.00',
       invoice_refs=['SYNTH-INV-DEMO-A'],sbisa=False,
       source_verified=True,bank_reference_verified=True),
  dict(source_kind='SYNTHETIC',utr='SYNTH-UTR-DEMO-B',sol_id='1505',
       client_name='SYNTH BRANCH',bank_date='2026-11-23',
       description='SYNTH POSTAGE NOVEMBER 2026',credit='125.50',
       invoice_refs=['SYNTH-INV-DEMO-A','SYNTH-INV-DEMO-B'],sbisa=False,
       source_verified=True,bank_reference_verified=True)
]
print(json.dumps(evaluate(fake_invoices,fake_payments,
                          activation_cutoff='2026-11-21',synthetic_only=True),
                 indent=2,sort_keys=True))