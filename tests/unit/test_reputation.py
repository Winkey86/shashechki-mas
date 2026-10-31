import unittest
from fractions import Fraction
from shashechki.reputation import rating, Ledger
class ReputationTests(unittest.TestCase):
    def test_prior(self):
        self.assertEqual(rating([]),Fraction(9,2))
        self.assertEqual(rating([{'value':3}]*10),Fraction(7,2))
    def test_verified_once(self):
        ledger=Ledger({'D':[]})
        self.assertFalse(ledger.record('D','C',5,'completed','forged'))
        self.assertFalse(ledger.record('D','forged',5,'completed','environment'))
        ledger.authorize('C',['D'],5,'completed')
        self.assertTrue(ledger.record('D','C',5,'completed','environment'))
        self.assertFalse(ledger.record('D','C',1,'breach','environment'))
        self.assertEqual(len(ledger.histories['D']),1)
        self.assertFalse(ledger.record('D','X',1,'system_cancel','environment'))
