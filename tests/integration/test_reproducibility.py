import unittest,copy
from shashechki.experiments import load_experiment,materialize
from shashechki.protocol import simulate
from shashechki.artifacts import digest
class ReproducibilityTests(unittest.TestCase):
    def test_materialization_and_independent_channels(self):
        e=load_experiment('scenarios/series/allocation.json');a=materialize(e,1,'normal');b=materialize(e,1,'normal');c=materialize(e,2,'normal')
        self.assertEqual(a,b);self.assertNotEqual(a['orders'],c['orders'])
        a['config']['allocation']='central';b['config']['allocation']='auction'
        aa=copy.deepcopy(a);bb=copy.deepcopy(b);aa.pop('config');bb.pop('config');self.assertEqual(digest(aa),digest(bb))
    def test_all_orders_accounted(self):
        e=load_experiment('scenarios/series/allocation.json');e['order_count']=10;s=materialize(e,0,'normal');r=simulate(s)
        self.assertEqual(sum(r.metrics[k]['value'] for k in ['completed','cancelled','expired','failed','censored']),10)
        self.assertEqual(len(r.drivers),10)
    def test_conflict_seeds_change_real_inputs(self):
        e=load_experiment('scenarios/series/negotiation.json');a=materialize(e,1,'controlled');b=materialize(e,2,'controlled')
        self.assertNotEqual(a['orders'],b['orders']);self.assertNotEqual(a['drivers'],b['drivers'])
