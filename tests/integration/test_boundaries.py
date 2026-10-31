import copy,unittest
from shashechki.protocol import simulate
from shashechki.validation import load
class BoundaryTests(unittest.TestCase):
    def test_budget_to_one_cent(self):
        s=load('scenarios/normal.json');s['passengers'][0]['budget']='258.00'
        self.assertEqual(simulate(s).orders[0]['outcome'],'completed')
        s['passengers'][0]['budget']='257.99';self.assertEqual(simulate(s).orders[0]['outcome'],'cancelled')
    def test_infeasible_class_route_and_rating(self):
        base=load('scenarios/normal.json')
        for mode in ['class','route','rating','no-drivers']:
            with self.subTest(mode=mode):
                s=copy.deepcopy(base)
                if mode=='class':s['orders'][0]['tariff_id']='comfort';s['drivers'][0]['vehicle_class']='economy'
                if mode=='route':s['city']['edges']=[]
                if mode=='rating':s['passengers'][0]['min_driver_rating']='5.00'
                if mode=='no-drivers':s['drivers']=[]
                r=simulate(s);self.assertNotEqual(r.orders[0]['outcome'],'completed');self.assertTrue(r.orders[0]['reason'])
        empty=simulate(load('scenarios/boundaries.json'));self.assertEqual(empty.metrics['orders']['value'],0);self.assertEqual(empty.metrics['service_rate']['reason'],'NO_ORDERS')
    def test_exact_wait_deadline(self):
        s=load('scenarios/normal.json');wait=simulate(s).orders[0]['wait_ms'];s['passengers'][0]['max_wait_ms']=wait
        self.assertEqual(simulate(s).orders[0]['outcome'],'completed')
        s['passengers'][0]['max_wait_ms']=wait-1;self.assertEqual(simulate(s).orders[0]['outcome'],'expired')
