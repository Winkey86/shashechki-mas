"""Политики получают локальный вид, не объект симуляции."""
from fractions import Fraction
from .pricing import cents, offer_price
from .reputation import rating

def driver_offer(driver,request,local):
    if local['offline'] or local['busy'] or driver.get('policy_id')=='withdraw':return None,'Водитель недоступен'
    if request['tariff']=='comfort' and driver['vehicle_class']!='comfort':return None,'Класс не соответствует тарифу'
    route,pickup=local['trip_route'],local['pickup_route']
    if route is None or pickup is None:return None,'Маршрут недостижим'
    price,floor=offer_price(driver,request['tariff'],route['distance_m'],route['travel_ms'],pickup['distance_m'],pickup['travel_ms'],request['passenger_rating'],request['rating_enabled'])
    return {'driver_id':driver['id'],'price':price,'floor':floor,'eta_ms':pickup['travel_ms'],
            'driver_rating':local['driver_rating'],'idle_since':local['idle_since']},'Цена покрывает индивидуальный порог'

def passenger_accept(passenger,offer,tariff,remaining_ms):
    return (tariff in passenger['allowed_tariffs'] and offer['price']<=cents(passenger['budget'])
            and offer['eta_ms']<=remaining_ms and offer['driver_rating']>=Fraction(passenger['min_driver_rating']))

def driver_counter(offer,price):return offer['floor']<=price<=offer['price']
