import unittest
from shashechki.validation import load
from shashechki.protocol import simulate
class FaultTests(unittest.TestCase):
    def pair(self,n):
        s=load(f'scenarios/fault-f{n}.json');s['config']['protection_profile']='baseline';a=simulate(s)
        s['config']['protection_profile']='protected';b=simulate(s);return a,b
    def test_all_faults_activate_and_protected_invariants(self):
        for n in range(1,8):
            with self.subTest(fault=n):
                a,b=self.pair(n)
                self.assertEqual(b.fault_results[0]['status'],'activated')
                self.assertEqual(b.metrics['violation_count']['value'],0)
                self.assertLessEqual(sum(x['kind']=='boarded' for x in b.trace),1)
    def test_reassignment(self):
        a,b=self.pair(1);self.assertEqual(a.orders[0]['outcome'],'expired');self.assertEqual(b.orders[0]['outcome'],'completed');self.assertEqual(b.orders[0]['version'],2)
    def test_tariff_and_conflict(self):
        for n in (2,4):
            a,b=self.pair(n);self.assertGreater(a.metrics['violation_count']['value'],0);self.assertEqual(b.metrics['violation_count']['value'],0)
    def test_postboarding_no_teleport(self):
        s=load('scenarios/fault-f1.json');s['faults'][0]['parameters']['delay_ms']=300000
        r=simulate(s);self.assertEqual(r.orders[0]['outcome'],'failed');self.assertEqual(r.metrics['revenue']['value'],'0.00')
        self.assertTrue(any(x['kind']=='simulation_stopped' for x in r.trace)==False)
    def test_tool_recovery(self):
        a,b=self.pair(6);self.assertEqual(a.metrics['completed']['value'],0);self.assertEqual(b.metrics['completed']['value'],1)

    def test_old_driver_message_cannot_restore_revoked_commit(self):
        from copy import deepcopy
        from shashechki.protocol import Simulation
        s=Simulation(load('scenarios/fault-f1.json'));s.run();o=next(iter(s.orders.values()));cid=o['commitment_id']
        old=deepcopy(next(e['details']['message'] for e in s.trace if e['kind']=='message_sent' and e['details']['message']['kind']=='CONFIRM'))
        old['id']='late-return';s.deliver(old)
        self.assertEqual(o['commitment_id'],cid);self.assertEqual(o['state'],'completed');self.assertEqual(s.trace[-1]['kind'],'message_rejected')
