import unittest
from shashechki.routes import Router
class RouteTests(unittest.TestCase):
    def test_route_and_disconnected(self):
        r=Router({'nodes':[{'id':s,'x':i,'y':0} for i,s in enumerate('ABC')],
                  'edges':[{'id':'AB','from':'A','to':'B','distance_m':100,'travel_ms':10}]})
        self.assertEqual(r.route('A','B')['distance_m'],100)
        self.assertIsNone(r.route('A','C'))
        self.assertEqual(r.route('A','A')['travel_ms'],0)
