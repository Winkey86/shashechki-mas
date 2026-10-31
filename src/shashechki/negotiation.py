"""Явные ценовые действия; состояние раундов хранит протокол."""
from .pricing import cents,TARIFFS

def counterprice(passenger,offers,tariff):
    minimum=TARIFFS[tariff]['minimum'];budget=cents(passenger['budget'])
    if not offers or budget<minimum:return None
    return max(minimum,min(budget,min(o['price'] for o in offers))-1000)
def next_price(driver,offer):
    return offer['price'] if driver.get('policy_id')=='hold' else max(offer['floor'],offer['price']-cents(driver['decrement']))
