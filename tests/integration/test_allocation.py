import unittest,copy
from shashechki.protocol import simulate
from shashechki.validation import load,validate
from shashechki.domain import InputError
class AllocationTests(unittest.TestCase):
    def test_equal_candidates_and_exclusive_commit(self):
        s=load('scenarios/playback-10.json')
        for d in s['drivers']:d['start_node']='N00';d['markup']='0.00'
        for mechanism in ('central','auction'):
            s['config']['allocation']=mechanism;r=simulate(s)
            self.assertEqual(r.orders[0]['driver_id'],'D00')
            self.assertEqual(sum(x['kind']=='confirmed' for x in r.trace),1)
            self.assertEqual(r.metrics['violation_count']['value'],0)
    def test_bad_fault_and_unknown_lists(self):
        s=load('scenarios/fault-f6.json');s['faults'][0]['parameters']['unavailable_to_ms']=1
        s['faults'][0]['trigger']['time_ms']=10
        with self.assertRaises(InputError):validate(s)
        s=load('scenarios/normal.json');s['orders']=None
        with self.assertRaises(InputError):validate(s)
