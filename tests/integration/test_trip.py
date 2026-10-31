import unittest,copy
from shashechki.validation import load
from shashechki.protocol import simulate
class TripTests(unittest.TestCase):
    def test_normal(self):
        r=simulate(load('scenarios/normal.json'))
        self.assertEqual(r.metrics['completed']['value'],1)
        self.assertEqual(r.metrics['violation_count']['value'],0)
        self.assertEqual(sum(int(float(d['revenue'])*100) for d in r.drivers),int(float(r.orders[0]['price'])*100))
        self.assertEqual(sum(x['kind']=='boarded' for x in r.trace),1)
    def test_two_allocators(self):
        s=load('scenarios/playback-10.json');r=simulate(s)
        s['config']['allocation']='auction';a=simulate(s)
        self.assertEqual(r.metrics['completed']['value'],1);self.assertEqual(a.metrics['completed']['value'],1)
    def test_no_budget(self):
        s=load('scenarios/normal.json');s['passengers'][0]['budget']='1.00'
        self.assertEqual(simulate(s).orders[0]['outcome'],'cancelled')
    def test_no_drivers(self):
        s=load('scenarios/normal.json');s['drivers']=[]
        self.assertEqual(simulate(s).metrics['completed']['value'],0)
    def test_canonical_repeat(self):
        s=load('scenarios/normal.json');a=simulate(s);b=simulate(s)
        self.assertEqual(a.trace,b.trace);self.assertEqual(a.metrics,b.metrics)
    def test_consent_boundary_and_duplicate_completion(self):
        from shashechki.protocol import Simulation
        s=Simulation(load('scenarios/normal.json'));o=next(iter(s.orders.values()));d=next(iter(s.drivers.values()));did=d['input']['id']
        offer=s.quote(d,o);o['selected']=offer;o['state']='awaiting_consent';o['consents']={did:{'price':offer['price'],'tariff':o['tariff_id']},o['passenger_id']:{'price':offer['price']-1,'tariff':o['tariff_id']}}
        s.commit(o,offer);self.assertFalse(s.commits)
        o['consents'][o['passenger_id']]['price']=offer['price'];s.e.now=o['deadline'];s.commit(o,offer);self.assertEqual(len(s.commits),1)
        s.commit(o,offer);self.assertEqual(len(s.commits),1)
        s=Simulation(load('scenarios/normal.json'));s.run();o=next(iter(s.orders.values()));d=s.drivers[o['driver_id']];revenue=d['revenue']
        s.complete(o,o['commitment_id'],o['driver_id']);s.board(o,o['commitment_id']);self.assertEqual(d['revenue'],revenue)
