"""Показатели с явными единицами, знаменателями и неопределимостью."""
from collections import Counter
from fractions import Fraction
import json
from .pricing import rounded,rubles,cost
from .domain import TERMINAL

def metric(value,unit,reason=None,n=None):
    out={'value':value,'unit':unit,'reason':reason}
    if n is not None:out['n']=n
    return out

def mean(values,unit):return metric(sum(values)/len(values) if values else None,unit,None if values else 'NO_OBSERVATIONS',len(values))
def jain(values):
    if not values:return metric(None,'ratio','NO_DRIVERS')
    total=sum(values);sq=sum(x*x for x in values)
    return metric(float(Fraction(total*total,len(values)*sq)) if sq else None,'ratio',None if sq else 'ALL_ZERO')
def json_default(value):
    if isinstance(value,Fraction):return {'numerator':value.numerator,'denominator':value.denominator}
    raise TypeError(type(value).__name__)
def measure(s):
    orders=[];drivers=[];counts=Counter()
    for o in s.orders.values():
        outcome=o['state'] if o['state'] in TERMINAL else 'censored';counts[outcome]+=1
        orders.append({'id':o['id'],'passenger_id':o['passenger_id'],'outcome':outcome,'state':o['state'],'reason':o['reason'],'version':o['version'],'driver_id':o.get('driver_id'),'price':rubles(o['price']) if 'price' in o else None,
            'assignment_ms':o['confirmed_at']-o['created_at_ms'] if 'confirmed_at' in o else None,'wait_ms':o['boarded_at']-o['created_at_ms'] if 'boarded_at' in o else None,
            'execution_ms':o['completed_at']-o['created_at_ms'] if 'completed_at' in o else None,'trip_ms':o['completed_at']-o['boarded_at'] if 'completed_at' in o else None,'rounds':o['round'],'tariff':o['tariff_id'],'tariff_changes':o['tariff_changes']})
    for i,d in s.drivers.items():
        expense=rounded(cost(d['input'],d['distance_m'],d['travel_ms']))
        drivers.append({'id':i,'completed':d['completed'],'revenue':rubles(d['revenue']),'cost':rubles(expense),'profit':rubles(d['revenue']-expense),'idle_ms':d['idle_ms'],'distance_m':float(d['distance_m']),'travel_ms':d['travel_ms']})
    m={key:metric(counts[key],'orders') for key in ('completed','cancelled','expired','failed','censored')}
    m['orders']=metric(len(orders),'orders');m['service_rate']=metric(counts['completed']/len(orders) if orders else None,'ratio',None if orders else 'NO_ORDERS')
    for key in ('assignment_ms','wait_ms','execution_ms','trip_ms'):m[key]=mean([o[key] for o in orders if o[key] is not None],'ms')
    kinds=Counter(x['kind'] for x in s.trace)
    for name,key in [('messages_sent','message_sent'),('messages_delivered','message_delivered'),('messages_dropped','message_dropped'),('messages_rejected','message_rejected')]:m[name]=metric(kinds[key],'messages')
    sent=[x['details']['message'] for x in s.trace if x['kind']=='message_sent']
    size=sum(len(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=json_default,allow_nan=False).encode()) for x in sent)
    m['bytes_sent']=metric(size,'bytes');m['coordination_cost']=metric(rubles(rounded(len(sent)+Fraction(size,1000)+s.decisions)),'RUB')
    m['model_processing_ms']=metric(s.decisions,'ms');m['model_end_ms']=metric(s.e.now,'ms')
    m['revenue']=metric(rubles(sum(d['revenue'] for d in s.drivers.values())),'RUB');m['cost']=metric(rubles(sum(rounded(cost(d['input'],d['distance_m'],d['travel_ms'])) for d in s.drivers.values())),'RUB')
    m['profit']=metric(rubles(sum(d['revenue']-rounded(cost(d['input'],d['distance_m'],d['travel_ms'])) for d in s.drivers.values())),'RUB')
    prices=[o['price'] for o in s.orders.values() if o['state']=='completed']
    m['final_price']=metric(rubles(rounded(Fraction(sum(prices),len(prices)))) if prices else None,'RUB',None if prices else 'NO_OBSERVATIONS',len(prices))
    m['Jain_revenue']=jain([d['revenue'] for d in s.drivers.values()]);m['violation_count']=metric(kinds['violation'],'events');m['attempt_count']=metric(kinds['violation_attempt'],'events');m['prevented_count']=metric(kinds['protection']+kinds['message_rejected'],'events')
    for group in ('low','middle','high'):
        ids=[i for i,r in s.initial_ratings.items() if i in s.people and ('low' if r<4 else ('middle' if r<=Fraction(9,2) else 'high'))==group]
        cohort=[o for o in orders if o['passenger_id'] in ids];n=sum(o['outcome']=='completed' for o in cohort)
        m['group_'+group]=metric(n/len(cohort) if cohort else None,'ratio',None if cohort else 'EMPTY_GROUP',len(cohort))
    for f in s.faults.results:
        activated=f['activated_at_ms'];events=[x for x in s.trace if activated is not None and x['time_ms']>=activated]
        detection=next((x['time_ms'] for x in events if x['kind'] in {'protection','message_rejected','tool_unavailable','reassigned'}),None)
        restored=next((x['time_ms'] for x in events if x['kind']=='confirmed' and x['time_ms']>activated),None) if f['type'] in {'F1','F6'} else None
        f['detection_ms']=detection-activated if detection is not None else None;f['recovery_ms']=restored-activated if restored is not None else None
        f['violations']=sum(x['kind']=='violation' for x in events);f['safe_stop']=counts['completed']==0 and f['violations']==0 and counts['censored']==0;f['resumed_service']=bool(restored is not None and counts['completed']);f['service_preserved']=bool(counts['completed'] and f['type'] not in {'F1','F6'});f['recovery_reason']=None if restored is not None else ('NOT_APPLICABLE' if f['type'] not in {'F1','F6'} else 'NOT_RECOVERED')
        f['limitation']='Правдоподобная ложь может быть не обнаружена' if f['type']=='F2' else ('Безопасная остановка не доказывает доступность' if f['type']=='F6' else 'Вывод ограничен данным воздействием и входами')
    return m,orders,drivers
