import copy,unittest
from shashechki.validation import load
from shashechki.protocol import simulate
class NegotiationTests(unittest.TestCase):
    def test_three_participants_and_counter(self):
        r=simulate(load('scenarios/conflict.json'))
        self.assertEqual(r.orders[0]['outcome'],'completed')
        self.assertLessEqual(r.orders[0]['rounds'],3)
        self.assertEqual(sum(x['kind']=='confirmed' for x in r.trace),1)
        self.assertTrue(any(x['kind']=='counter_proposed' for x in r.trace))
        self.assertEqual(sum(x['kind']=='counter_reply' for x in r.trace),2)
    def test_tariff_version(self):
        r=simulate(load('scenarios/tariff-switch.json'))
        self.assertEqual(r.orders[0]['tariff'],'economy');self.assertEqual(r.orders[0]['version'],2)
        self.assertEqual(r.orders[0]['tariff_changes'],1)
        self.assertEqual(r.orders[0]['outcome'],'completed')
    def test_no_agreement_and_hold(self):
        s=load('scenarios/conflict.json');s['passengers'][0]['budget']='1.00'
        for d in s['drivers']:d['policy_id']='hold'
        r=simulate(s);self.assertEqual(r.orders[0]['outcome'],'cancelled');self.assertLessEqual(r.orders[0]['rounds'],3)
        from fractions import Fraction
        self.assertLess(Fraction(r.metrics['profit']['value']),0)
    def test_first_acceptable(self):
        s=load('scenarios/conflict.json');s['config']['conflict_policy']='first_acceptable'
        r=simulate(s);self.assertEqual(r.orders[0]['outcome'],'completed')
        self.assertFalse(any(x['kind']=='counter_proposed' for x in r.trace))
        for d in s['drivers']:d['policy_id']='withdraw'
        declined=simulate(s);self.assertNotEqual(declined.orders[0]['outcome'],'completed')
        self.assertFalse(any(x['kind']=='confirmed' for x in declined.trace))
