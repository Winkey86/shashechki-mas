"""Строгая проверка входов до постановки задания в очередь."""
from copy import deepcopy
from fractions import Fraction
import json
from .domain import InputError, DEFAULT_CONFIG, ID_PATTERN, SCHEMA_VERSION
from .pricing import cents

def require(ok,message,path=''):
    if not ok:raise InputError(message,path)
def fields(obj,required,optional=(),path=''):
    require(isinstance(obj,dict),'Ожидается объект',path)
    require(not(set(obj)-set(required)-set(optional)),'Неизвестные поля: '+', '.join(sorted(set(obj)-set(required)-set(optional))),path)
    require(set(required)<=obj.keys(),'Отсутствуют обязательные поля',path)
def integer(x,path,minimum=0):require(type(x) is int and x>=minimum,'Ожидается целое число в допустимом диапазоне',path)
def identifier(x,path):require(isinstance(x,str) and bool(ID_PATTERN.fullmatch(x)),'Недопустимый идентификатор',path)
def money(x,path):
    try:return cents(x)
    except ValueError as exc:raise InputError(str(exc),path) from exc

def config(value):
    fields(value,(),DEFAULT_CONFIG.keys(),'config');out=deepcopy(DEFAULT_CONFIG)
    for k,v in value.items():
        if isinstance(out[k],dict):
            fields(v,(),out[k].keys(),'config.'+k);out[k].update(v)
        else:out[k]=v
    for k,choices in {'allocation':{'central','auction'},'conflict_policy':{'first_acceptable','negotiation'},'rating_policy':{'off','fixed','dynamic'},'protection_profile':{'baseline','protected'}}.items():
        require(isinstance(out[k],str) and out[k] in choices,'Неизвестный режим','config.'+k)
    for group in ('limits','deadlines'):
        for k,v in out[group].items():integer(v,'config.'+group+'.'+k,0 if k=='max_reassignments' else 1)
    require(out['deadlines']['max_rounds']<=3,'Максимум три раунда','config.deadlines.max_rounds')
    require(out['deadlines']['max_reassignments']<=2,'Максимум два переназначения','config.deadlines.max_reassignments')
    require(out['limits']['horizon_ms']<=86400000 and out['limits']['max_events']<=1000000 and out['limits']['max_pending_events']<=100000,'Превышен технический предел','config.limits')
    w=out['weights']['wait_kopecks_per_ms'];fields(w,('numerator','denominator'),path='config.weights')
    integer(w['numerator'],'weights.numerator');integer(w['denominator'],'weights.denominator',1)
    integer(out['weights']['driver_rating_kopecks'],'weights.rating')
    return out

def validate(data):
    required=('schema_version','scenario_id','city','drivers','passengers','orders','channel_profile','faults','config')
    fields(data,required,('title','description','provenance'))
    if data['schema_version']!=SCHEMA_VERSION:raise InputError('Неподдерживаемая версия схемы','schema_version','UNSUPPORTED_SCHEMA')
    identifier(data['scenario_id'],'scenario_id');city=data['city'];fields(city,('id','nodes','edges'),path='city')
    for key in ('drivers','passengers','orders','channel_profile','faults'):
        require(isinstance(data[key],list),'Ожидается массив',key)
    for key in ('nodes','edges'):require(isinstance(city[key],list),'Ожидается массив','city.'+key)
    identifier(city['id'],'city.id');node_ids=set();edge_ids=set()
    for n in city['nodes']:
        fields(n,('id','x','y'),path='city.nodes');identifier(n['id'],'node.id');require(n['id'] not in node_ids,'Повтор узла','city.nodes');node_ids.add(n['id'])
        for k in ('x','y'):require(type(n[k]) is int and abs(n[k])<=1000000,'Недопустимая координата','node.'+k)
    require(bool(node_ids),'Граф должен содержать хотя бы один узел','city.nodes')
    for e in city['edges']:
        fields(e,('id','from','to','distance_m','travel_ms'),path='city.edges');identifier(e['id'],'edge.id')
        require(e['id'] not in edge_ids,'Повтор ребра','edge.id');edge_ids.add(e['id'])
        require(e['from'] in node_ids and e['to'] in node_ids,'Неизвестный узел ребра','edge')
        integer(e['distance_m'],'edge.distance_m',1);integer(e['travel_ms'],'edge.travel_ms',1)
    all_ids={'dispatcher'};drivers=set();passengers=set()
    for role,items in (('driver',data['drivers']),('passenger',data['passengers'])):
        require(isinstance(items,list),'Ожидается массив',role)
        for a in items:
            keys=('id','start_node','vehicle_class','cost_per_km','cost_per_min','minimum_profit','markup','decrement','rating_history') if role=='driver' else ('id','budget','max_wait_ms','allowed_tariffs','min_driver_rating','rating_history')
            fields(a,keys,(('policy_id','unavailable_until_ms') if role=='driver' else ()),role);identifier(a['id'],role+'.id');require(a['id'] not in all_ids,'Повтор агента',role+'.id');all_ids.add(a['id'])
            (drivers if role=='driver' else passengers).add(a['id'])
            require(isinstance(a['rating_history'],list),'Ожидается массив',role+'.rating_history')
            for h in a['rating_history']:
                fields(h,('id','value','cause','commitment_id','source_event_id','origin'),path=role+'.history')
                require(type(h['value']) is int and 1<=h['value']<=5 and h['origin']=='fixture','Некорректная начальная история',role+'.history')
            require(len({h['id'] for h in a['rating_history']})==len(a['rating_history']),'Повтор события истории',role+'.history')
            if role=='driver':
                if 'unavailable_until_ms' in a:integer(a['unavailable_until_ms'],role+'.unavailable_until_ms')
                require(a['start_node'] in node_ids,'Неизвестная позиция',role)
                require(a['vehicle_class'] in {'economy','comfort'},'Неизвестный класс',role)
                for k in ('cost_per_km','cost_per_min','minimum_profit','markup','decrement'):money(a[k],role+'.'+k)
                require(a.get('policy_id','normal') in {'normal','hold','withdraw'},'Неизвестная стратегия',role)
            else:
                money(a['budget'],role+'.budget');integer(a['max_wait_ms'],role+'.max_wait_ms',1)
                require(isinstance(a['allowed_tariffs'],list) and bool(a['allowed_tariffs']) and set(a['allowed_tariffs'])<={'economy','comfort'},'Недопустимые тарифы',role)
                try:r=Fraction(a['min_driver_rating'])
                except (ValueError,TypeError,ZeroDivisionError) as exc:raise InputError('Неверный рейтинг',role) from exc
                require(1<=r<=5,'Рейтинг вне диапазона',role)
    order_ids=set();order_people=set()
    for o in data['orders']:
        fields(o,('id','passenger_id','created_at_ms','origin','destination','tariff_id'),('candidate_ids',),'order')
        identifier(o['id'],'order.id');require(o['id'] not in order_ids,'Повтор заказа','order.id');order_ids.add(o['id'])
        require(o['passenger_id'] in passengers and o['passenger_id'] not in order_people,'Неизвестный пассажир либо повторный заказ','order.passenger_id');order_people.add(o['passenger_id'])
        integer(o['created_at_ms'],'order.created_at_ms');require(o['origin'] in node_ids and o['destination'] in node_ids,'Неизвестная точка','order')
        p=next(x for x in data['passengers'] if x['id']==o['passenger_id'])
        require(o['tariff_id'] in p['allowed_tariffs'],'Тариф не разрешён пассажиром','order.tariff_id')
        if 'candidate_ids' in o:require(isinstance(o['candidate_ids'],list) and all(isinstance(i,str) for i in o['candidate_ids']) and len(o['candidate_ids'])==2 and len(set(o['candidate_ids']))==2 and set(o['candidate_ids'])<=drivers,'Нужны два разных известных кандидата','order.candidate_ids')
    for c in data['channel_profile']:
        fields(c,('channel','from_ms','to_ms','delay_ms','drop','duplicate_count','duplicate_offset_ms'),path='channel_profile')
        for k in ('from_ms','to_ms','duplicate_count'):integer(c[k],'channel.'+k)
        integer(c['delay_ms'],'channel.delay_ms',1);integer(c['duplicate_offset_ms'],'channel.duplicate_offset_ms',1)
        require(c['to_ms']>c['from_ms'] and type(c['drop']) is bool and c['duplicate_count']<=10,'Неверный профиль связи','channel')
    for channel in {c['channel'] for c in data['channel_profile']}:
        records=sorted((c for c in data['channel_profile'] if c['channel']==channel),key=lambda c:c['from_ms'])
        require(all(a['to_ms']<=b['from_ms'] for a,b in zip(records,records[1:])),'Пересекающиеся интервалы','channel_profile')
    fault_ids=set()
    for f in data['faults']:
        fields(f,('id','type','trigger','target','parameters'),path='fault');identifier(f['id'],'fault.id')
        require(f['id'] not in fault_ids,'Повтор воздействия','fault.id');fault_ids.add(f['id'])
        require(f['type'] in {f'F{i}' for i in range(1,8)},'Неизвестное воздействие','fault.type')
        fields(f['trigger'],('kind',),('time_ms','message_kind'),'fault.trigger')
        require(f['trigger']['kind'] in {'time','after_confirm','message','negotiation'},'Неизвестный триггер','fault.trigger')
        if f['trigger']['kind']=='time':integer(f['trigger'].get('time_ms'),'fault.trigger.time_ms')
        require(f['target'] in all_ids or f['target']=='first_matching','Неизвестная цель','fault.target')
        fields(f['parameters'],(),('mode','field','replacement','count','delay_ms','tool','unavailable_to_ms','forged_value','asserted_source'),'fault.parameters')
        p=f['parameters'];kind=f['type'];trigger=f['trigger']['kind']
        for key in ('count','delay_ms','unavailable_to_ms'):
            if key in p:integer(p[key],'fault.parameters.'+key,1)
        require(p.get('count',2)<=10,'Максимум десять копий','fault.parameters.count')
        if kind=='F2':
            require(p.get('field','price') in ('price','position','eta'),'Неизвестное поле подмены','fault.parameters.field')
            field=p.get('field','price')
            if field=='price':money(p.get('replacement','99.00'),'fault.parameters.replacement')
            elif field=='position':require(p.get('replacement') in node_ids,'Неизвестный узел','fault.parameters.replacement')
            else:integer(p.get('replacement',0),'fault.parameters.replacement')
        if kind=='F3':require(p.get('mode','duplicate') in ('duplicate','delay'),'Неизвестный режим','fault.parameters.mode')
        if kind=='F4':require(p.get('mode','conflicting') in ('conflicting','unauthorized'),'Неизвестный режим','fault.parameters.mode')
        if kind=='F5':require(p.get('mode','loop') in ('loop','breach'),'Неизвестный режим','fault.parameters.mode')
        if kind=='F6':
            require(trigger=='time' and p.get('tool','dispatcher') in ('dispatcher','router'),'Недопустимое средство или триггер','fault.parameters.tool')
            require(p.get('unavailable_to_ms',20000)>f['trigger']['time_ms'],'Восстановление должно следовать после отказа','fault.parameters.unavailable_to_ms')
        if kind=='F7':
            require(type(p.get('forged_value',5)) is int and 1<=p.get('forged_value',5)<=5,'Рейтинг вне диапазона','fault.parameters.forged_value')
            require(isinstance(p.get('asserted_source','agent'),str),'Ожидается строка источника','fault.parameters.asserted_source')
    result=deepcopy(data);result['config']=config(data['config']);return result

def load(path):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise InputError('Повтор ключа JSON',k)
            out[k]=v
        return out
    try:
        with open(path,encoding='utf-8') as f:data=json.load(f,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(InputError('NaN/Infinity запрещены')))
    except (OSError,json.JSONDecodeError,UnicodeError) as exc:raise InputError('Не удалось прочитать JSON: '+str(exc)) from exc
    return validate(data)
