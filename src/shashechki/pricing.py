"""Деньги: копейки на границах, точные дроби внутри формул."""
from fractions import Fraction
import re
TARIFFS = {
 'economy': {'title':'Эконом','base':10000,'per_km':1800,'per_min':400,'minimum':20000},
 'comfort': {'title':'Комфорт','base':16000,'per_km':2500,'per_min':600,'minimum':30000},
}
def cents(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d{1,2})?',value):
        raise ValueError('Денежная сумма должна быть неотрицательной строкой с точностью до копейки')
    return int(Fraction(value)*100)
def rubles(value):
    n=int(value);return ('-' if n<0 else '')+f'{abs(n)//100}.{abs(n)%100:02d}'
def rounded(value):
    q=Fraction(value);sign=-1 if q<0 else 1;q=abs(q)
    return sign*((q.numerator*2+q.denominator)//(2*q.denominator))
def ceil(value):
    q=Fraction(value);return -(-q.numerator//q.denominator)
def base_price(tariff,distance_m,travel_ms):
    t=TARIFFS[tariff]
    return rounded(max(t['minimum'],t['base']+Fraction(t['per_km']*distance_m,1000)+Fraction(t['per_min']*travel_ms,60000)))
def start_price(tariff,distance_m,travel_ms,passenger_rating,enabled):
    base=base_price(tariff,distance_m,travel_ms)
    surcharge=min(Fraction(15,100),Fraction(1,10)*max(0,Fraction(9,2)-passenger_rating)) if enabled else 0
    return rounded(base*(1+surcharge))
def cost(driver,distance_m,travel_ms):
    return Fraction(cents(driver['cost_per_km'])*distance_m,1000)+Fraction(cents(driver['cost_per_min'])*travel_ms,60000)
def offer_price(driver,tariff,trip_m,trip_ms,pickup_m,pickup_ms,passenger_rating,enabled):
    floor=max(TARIFFS[tariff]['minimum'],ceil(cost(driver,trip_m+pickup_m,trip_ms+pickup_ms)+cents(driver['minimum_profit'])))
    return max(floor,start_price(tariff,trip_m,trip_ms,passenger_rating,enabled)+cents(driver['markup'])),floor
