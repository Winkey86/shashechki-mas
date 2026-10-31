import unittest
from fractions import Fraction
from shashechki.pricing import cents, rubles, base_price, start_price, offer_price, cost
from shashechki.reputation import rating

class PricingTests(unittest.TestCase):
    def test_exact_examples(self):
        self.assertEqual(base_price('economy',5000,720000),23800)
        self.assertEqual(base_price('comfort',5000,720000),35700)
        self.assertEqual(start_price('economy',5000,720000,Fraction(7,2),True),26180)
        self.assertEqual(start_price('economy',5000,720000,Fraction(29,6),True),23800)
    def test_boundaries(self):
        self.assertEqual(cents('0.01'),1)
        from shashechki.pricing import rounded,ceil
        self.assertEqual(rounded(Fraction(1,2)),1);self.assertEqual(rounded(Fraction(-1,2)),-1);self.assertEqual(ceil(Fraction(30001,1000)),31)
        self.assertEqual(rubles(-12),'-0.12')
        for value in ['NaN','1.001','-1.00',1.2]:
            with self.assertRaises(ValueError):cents(value)
    def test_floor_and_exact_cost(self):
        d={'cost_per_km':'8.00','cost_per_min':'1.00','minimum_profit':'30.00','markup':'10.00'}
        price,floor=offer_price(d,'economy',5000,720000,1000,120000,Fraction(9,2),False)
        self.assertGreaterEqual(price,floor)
        self.assertEqual(cost(d,6000,840000),6200)
