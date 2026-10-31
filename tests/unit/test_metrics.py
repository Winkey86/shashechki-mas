import unittest
from shashechki.metrics import jain
class MetricsTests(unittest.TestCase):
    def test_jain(self):
        self.assertEqual(jain([100,100])['value'],1)
        self.assertEqual(jain([100,0])['value'],.5)
        self.assertIsNone(jain([0,0])['value']);self.assertEqual(jain([0,0])['reason'],'ALL_ZERO')
    def test_money_and_missing_observations(self):
        from shashechki.experiments import pair_summary
        pairs=[{'condition':'c','complete':True,'a_metrics':{'price':{'value':'0.01','unit':'RUB'},'wait':{'value':10,'unit':'ms'}},'b_metrics':{'price':{'value':'0.02','unit':'RUB'},'wait':{'value':None,'unit':'ms'}}}]
        summary=pair_summary(pairs)['c']
        self.assertEqual(summary['price']['delta_mean'],'0.01')
        self.assertEqual(summary['wait']['a_mean'],10);self.assertIsNone(summary['wait']['b_mean']);self.assertEqual(summary['wait']['n'],0)
    def test_empty_censored_and_traffic_cost(self):
        from fractions import Fraction
        from shashechki.protocol import simulate
        from shashechki.validation import load
        from shashechki.artifacts import canonical
        from shashechki.pricing import rounded,rubles
        s=load('scenarios/boundaries.json');r=simulate(s)
        self.assertIsNone(r.metrics['service_rate']['value'])
        s=load('scenarios/normal.json');s['config']['limits']['max_events']=1;r=simulate(s)
        self.assertEqual(r.metrics['censored']['value'],1);self.assertEqual(r.termination_reason,'limit_reached')
        r=simulate(load('scenarios/normal.json'));sent=[e['details']['message'] for e in r.trace if e['kind']=='message_sent'];decisions=sum(e['kind']=='decision' for e in r.trace)
        size=sum(len(canonical(m)) for m in sent)
        self.assertEqual(r.metrics['bytes_sent']['value'],size)
        self.assertEqual(r.metrics['coordination_cost']['value'],rubles(rounded(len(sent)+Fraction(size,1000)+decisions)))
