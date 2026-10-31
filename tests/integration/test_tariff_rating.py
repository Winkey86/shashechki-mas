import unittest
from shashechki.protocol import simulate
from shashechki.validation import load
class TariffRatingTests(unittest.TestCase):
    def test_confirmed_price_is_frozen(self):
        s=load('scenarios/conflict.json');r=simulate(s)
        order=r.orders[0];self.assertEqual(order['price'],'261.80')
        s['config']['rating_policy']='dynamic';dynamic=simulate(s)
        self.assertEqual(dynamic.orders[0]['price'],order['price'])
        s=load('scenarios/tariff-switch.json');r=simulate(s)
        self.assertEqual(r.orders[0]['tariff'],'economy');self.assertEqual(r.orders[0]['version'],2)
