import unittest
from shashechki.engine import Engine
class EngineTests(unittest.TestCase):
    def test_phase_boundary_and_sequence(self):
        e=Engine();out=[]
        for phase,name in [(4,'timeout'),(2,'reply'),(3,'close'),(2,'reply2')]:
            e.schedule(100,phase,lambda name=name:out.append(name))
        e.run()
        self.assertEqual(out,['reply','reply2','close','timeout'])
    def test_limits(self):
        e=Engine(max_events=3)
        def again():e.schedule(e.now+1,1,again)
        e.schedule(0,1,again);e.run()
        self.assertEqual(e.termination,'limit_reached')
    def test_no_retroactive_event(self):
        e=Engine()
        def bad():
            with self.assertRaises(ValueError):e.schedule(0,1,lambda:None)
        e.schedule(0,3,bad);e.run()
