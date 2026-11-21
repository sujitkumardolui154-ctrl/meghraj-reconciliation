"""All identifiers/amounts are independently invented; no bank workbook used."""
import copy
import unittest
from sbi_engine import evaluate, EngineBlocked
from sbi_engine.engine import narration_period

CUT='2026-11-21'

def invoice(n='SYNTH-INV-A', sol='1505',client='SYNTH SOUTHERN AVENUE',
            taxable='100.00',cgst='9.00',sgst='9.00',gross='118.00',rate=1,
            issued='2026-11-21',months=None,sbisa=False,paid=None,protected=False,
            note=False,verified=True,master=True):
    return dict(source_kind='SYNTHETIC',invoice_no=n,sol_id=sol,client_name=client,
        taxable=taxable,cgst=cgst,sgst=sgst,gross=gross,approved_tds_rate=rate,
        invoice_date=issued,service_months=months or ['2026-11'],sbisa=sbisa,
        original_paid_marker=paid,protected_prior=protected,credit_note=note,
        source_verified=verified,master_verified=master)

def pay(utr='SYNTH-UTR-A',refs=None,credit='117.00',sol='1505',
        client='SYNTH SOUTHERN AVENUE',date='2026-11-22',
        desc='SYNTH POSTAGE NOVEMBER 2026',sbisa=False,verified=True,bank=True):
    return dict(source_kind='SYNTHETIC',utr=utr,invoice_refs=['SYNTH-INV-A'] if refs is None else refs,
        sol_id=sol,client_name=client,bank_date=date,credit=credit,
        description=desc,sbisa=sbisa,source_verified=verified,bank_reference_verified=bank)

def run(ins=None,pays=None,**kw):
    return evaluate([invoice()] if ins is None else ins,[pay()] if pays is None else pays,
                    activation_cutoff=CUT,synthetic_only=True,**kw)

class FreshEngineTests(unittest.TestCase):
    def test_one_to_one_full(self):
        x=run()
        self.assertEqual(x['proposal_count'],1)
        self.assertEqual(x['proposals'][0]['candidate_credit'],'117.00')
        self.assertEqual(x['proposals'][0]['candidate_status'],'PROPOSED_FULL')
        self.assertFalse(x['financial_writes'])
        self.assertFalse(x['historical_records_accessed'])
        self.assertEqual(x['actual_financial_status'],'NOT_ASSIGNED')

    def test_partial_then_full(self):
        x=run(pays=[pay(credit='50.00'),pay('SYNTH-UTR-B',credit='67.00',date='2026-11-23')])
        self.assertEqual([v['candidate_status'] for v in x['proposals']],
                         ['PROPOSED_PARTIAL','PROPOSED_FULL'])
        self.assertEqual(x['remaining_net']['SYNTH-INV-A'],'0.00')

    def test_wrong_sol(self):
        self.assertEqual(run(pays=[pay(sol='1506')])['holds'][0]['reason'],'CROSS_SOL_FORBIDDEN')

    def test_exact_sol_not_numeric_normalized(self):
        self.assertEqual(run(pays=[pay(sol='01505')])['holds'][0]['reason'],'CROSS_SOL_FORBIDDEN')

    def test_wrong_client(self):
        self.assertEqual(run(pays=[pay(client='SYNTH OTHER')])['holds'][0]['reason'],'CLIENT_IDENTITY_CONFLICT')

    def test_period_parsers(self):
        for text,expect in [('AUG-26',{'2026-08'}),('August 2026',{'2026-08'}),
            ('08-2026',{'2026-08'}),('Mar-May 2026',{'2026-03','2026-04','2026-05'}),
            ('March to May2026',{'2026-03','2026-04','2026-05'})]:
            with self.subTest(text=text):
                self.assertEqual(narration_period('BULK POSTING '+text),frozenset(expect))

    def test_multi_month_exact(self):
        x=run(ins=[invoice(months=['2026-03','2026-04','2026-05'])],
          pays=[pay(desc='SYNTH POSTAGE Mar-May 2026')])
        self.assertEqual(x['proposal_count'],1)

    def test_period_contradiction(self):
        x=run(pays=[pay(desc='SYNTH CHARGE OCT-26')]);self.assertEqual(x['holds'][0]['reason'],'CONTRADICTORY_SERVICE_PERIOD')

    def test_missing_period(self):
        x=run(pays=[pay(desc='SYNTH POSTAGE NO PERIOD')]);self.assertEqual(x['holds'][0]['reason'],'SERVICE_PERIOD_EVIDENCE_MISSING')

    def test_multiple_periods_rejected(self):
        with self.assertRaises(EngineBlocked):run(pays=[pay(desc='JAN-26 AND FEB-26')])

    def test_pre_cutoff_payment(self):
        x=run(pays=[pay(date='2026-11-20')]);self.assertEqual(x['holds'][0]['reason'],'PRE_ACTIVATION_PAYMENT')

    def test_pre_cutoff_invoice(self):
        x=run(ins=[invoice(issued='2026-11-20')]);self.assertEqual(x['holds'][0]['reason'],'PRE_ACTIVATION_INVOICE')

    def test_paid_marker_numeric_zero_protected(self):
        x=run(ins=[invoice(paid=0)]);self.assertEqual(x['holds'][0]['reason'],'PAID_OR_PROTECTED_SOURCE')

    def test_protected_prior_allocation(self):
        x=run(ins=[invoice(protected=True)]);self.assertEqual(x['proposal_count'],0)

    def test_credit_note(self):
        x=run(ins=[invoice(note=True)]);self.assertEqual(x['holds'][0]['reason'],'CREDIT_NOTE_REVIEW')

    def test_duplicate_payment_ids_both_held(self):
        x=run(pays=[pay(),pay()]);self.assertEqual(x['proposal_count'],0)
        self.assertEqual(len(x['holds']),2)

    def test_duplicate_invoice_no_held(self):
        x=run(ins=[invoice(),invoice()]);self.assertEqual(x['holds'][0]['reason'],'DUPLICATE_INVOICE_NUMBER')

    def test_duplicate_invoice_no_cannot_be_ignored_without_ref(self):
        ins=[invoice(),invoice(),invoice('SYNTH-INV-B')]
        x=run(ins=ins,pays=[pay(refs=[])])
        self.assertEqual(x['proposal_count'],0)
        self.assertEqual(x['holds'][0]['reason'],'DUPLICATE_INVOICE_NUMBER')

    def test_contradictory_invoice_number_in_narration(self):
        x=run(pays=[pay(desc='SYNTH-INV-B NOVEMBER 2026')])
        self.assertEqual(x['proposal_count'],0)
        self.assertEqual(x['holds'][0]['reason'],'CONTRADICTORY_OR_UNVERIFIED_INVOICE_NARRATION')

    def test_unreferenced_narration_invoice_number_holds(self):
        x=run(pays=[pay(refs=[],desc='SYNTH-INV-A NOVEMBER 2026')])
        self.assertEqual(x['proposal_count'],0)
        self.assertEqual(x['holds'][0]['reason'],'CONTRADICTORY_OR_UNVERIFIED_INVOICE_NARRATION')

    def test_unverified_bank_proof(self):
        x=run(pays=[pay(bank=False)]);self.assertEqual(x['holds'][0]['reason'],'BANK_PROVENANCE_UNVERIFIED')

    def test_unverified_branch_master(self):
        x=run(ins=[invoice(master=False)]);self.assertEqual(x['holds'][0]['reason'],'SOURCE_OR_MASTER_NOT_VERIFIED')

    def test_overpayment_atomic(self):
        x=run(pays=[pay(credit='50.00'),pay('SYNTH-UTR-B',credit='80.00',date='2026-11-23')])
        self.assertEqual(x['proposal_count'],1)
        self.assertEqual(x['remaining_net']['SYNTH-INV-A'],'67.00')
        self.assertEqual(x['holds'][0]['reason'],'OVERPAYMENT_OR_DUPLICATE_CREDIT')

    def test_split_waterfall_explicit_order(self):
        ins=[invoice(),invoice('SYNTH-INV-B',taxable='50.00',cgst='4.50',sgst='4.50',gross='59.00')]
        x=run(ins=ins,pays=[pay(refs=['SYNTH-INV-A','SYNTH-INV-B'],credit='175.50')])
        self.assertEqual(x['proposal_count'],2)
        self.assertEqual([p['candidate_credit'] for p in x['proposals']],['117.00','58.50'])

    def test_ambiguous_no_ref(self):
        ins=[invoice(),invoice('SYNTH-INV-B')]
        x=run(ins=ins,pays=[pay(refs=[])])
        self.assertEqual(x['holds'][0]['reason'],'AMBIGUOUS_SAME_SOL_CANDIDATES')
        self.assertEqual(x['proposal_count'],0)

    def test_no_ref_unique_exact(self):
        x=run(pays=[pay(refs=[])])
        self.assertEqual(x['proposal_count'],1)

    def test_dnm_review_never_auto_ok(self):
        ins=[invoice(issued='2026-11-22'),invoice('SYNTH-INV-B',taxable='200',cgst='18',sgst='18',gross='236')]
        x=run(ins=ins,pays=[pay(refs=[],credit='116.50')])
        self.assertEqual(x['proposal_count'],0)
        self.assertEqual(x['holds'][0]['reason'],'DNM01_OR_PARTIAL_REVIEW_REQUIRED')
        self.assertTrue(x['holds'][0]['provisional_dnm01'])

    def test_dnm_requires_strict_recency(self):
        ins=[invoice(),invoice('SYNTH-INV-B',taxable='200',cgst='18',sgst='18',gross='236')]
        x=run(ins=ins,pays=[pay(refs=[],credit='116.50')])
        self.assertEqual(x['proposal_count'],0)
        self.assertFalse(x['holds'][0]['provisional_dnm01'])

    def test_sbisa_collect_sol_one_blank_invoice(self):
        ins=[invoice(sol='',client='SYNTH SBISA',sbisa=True)]
        x=run(ins=ins,pays=[pay(sol='1',client='SYNTH SBISA',sbisa=True)])
        self.assertEqual(x['proposal_count'],1)

    def test_sbisa_false_cannot_cross(self):
        ins=[invoice(sol='',client='SYNTH SBISA',sbisa=True)]
        x=run(ins=ins,pays=[pay(sol='1',client='SYNTH SBISA',sbisa=False)])
        self.assertEqual(x['proposal_count'],0)

    def test_gst_narration_allowed(self):
        self.assertEqual(run(pays=[pay(desc='GST POSTAGE NOV-26')])['proposal_count'],1)

    def test_tds_half_up(self):
        x=run(ins=[invoice(taxable='0.50',cgst='0',sgst='0',gross='0.50')],pays=[pay(credit='0.49')])
        self.assertEqual(x['proposal_count'],1)

    def test_reject_real_data_without_read(self):
        for target,change in [('invoice_no','MXP1001'),('source_kind','REAL')]:
            with self.subTest(target=target):
                i=invoice();i[target]=change
                with self.assertRaises(EngineBlocked):run(ins=[i])
        p=pay();p['utr']='REALBANK123'
        with self.assertRaises(EngineBlocked):run(pays=[p])
        with self.assertRaises(EngineBlocked):evaluate([invoice()],[pay()],activation_cutoff=CUT)

    def test_no_input_mutation_and_deterministic(self):
        i,p=invoice(),pay();before=copy.deepcopy((i,p))
        self.assertEqual(run([i],[p]),run([i],[p]))
        self.assertEqual((i,p),before)

    def test_tds_all_explicit_rates(self):
        # The 1%/2%/3% deductions are computed from taxable, not gross.
        for rate,net in [(0,'118.00'),(1,'117.00'),(2,'116.00'),(3,'115.00')]:
            with self.subTest(rate=rate):
                x=run(ins=[invoice(rate=rate)],pays=[pay(credit=net)])
                self.assertEqual(x['proposal_count'],1)
                self.assertEqual(x['remaining_net']['SYNTH-INV-A'],'0.00')

    def test_180_day_window_enforced(self):
        # Deliberately beyond 180 days; no old data is read.
        x=run(pays=[pay(date='2027-07-01')])
        self.assertEqual(x['proposal_count'],0)
        self.assertEqual(x['holds'][0]['reason'],'OUTSIDE_APPROVED_180_DAY_WINDOW')

    def test_fully_proposed_invoice_cannot_get_second_full_credit(self):
        x=run(pays=[pay(),pay('SYNTH-UTR-B',date='2026-11-23')])
        self.assertEqual(x['proposal_count'],1)
        self.assertEqual(x['holds'][0]['reason'],'ALREADY_SATISFIED_IN_THIS_SIMULATION')

    def test_withheld_source_credit_does_not_substitute_debit(self):
        p=pay(credit='0.00')
        with self.assertRaises(EngineBlocked):run(pays=[p])

    def test_invalid_rate_never_guessed(self):
        for r in (None,'1',4,-1,True):
            with self.subTest(rate=r):
                with self.assertRaises(EngineBlocked):run(ins=[invoice(rate=r)])

    def test_invalid_decimal_no_float(self):
        with self.assertRaises(EngineBlocked):run(pays=[pay(credit=117.0)])

if __name__=='__main__':unittest.main()