"""Общие фильтры и обобщённая стоимость двух механизмов."""
from fractions import Fraction
from .agents import passenger_accept

def score(offer,weights):
    w=weights['wait_kopecks_per_ms'];alpha=Fraction(w['numerator'],w['denominator'])
    return offer['price']+alpha*offer['eta_ms']+weights['driver_rating_kopecks']*(5-offer['driver_rating'])
def ranked(offers,passenger,tariff,remaining_ms,weights):
    valid=[o for o in offers if passenger_accept(passenger,o,tariff,remaining_ms)]
    return sorted(valid,key=lambda o:(score(o,weights),o['idle_since'],o['driver_id']))
