"""Общий протокол исполнения: локальные политики, сообщения, версии и атомарный commit."""
from copy import deepcopy
from fractions import Fraction
from bisect import bisect_right
from .domain import Agent,Run,TERMINAL
from .engine import Engine
from .routes import Router
from .pricing import cents,rubles,rounded,cost,base_price,start_price,TARIFFS
from .reputation import Ledger,rating
from .agents import driver_offer,passenger_accept,driver_counter
from .allocation import ranked
from .negotiation import next_price,counterprice
from .projection import Projection
from .validation import validate

class Simulation:
    def __init__(self,inputs,cancel=None):
        self.inputs=validate(inputs);self.config=self.inputs['config'];self.protected=self.config['protection_profile']=='protected'
        self.e=Engine(**self.config['limits'],cancel=cancel);self.router=Router(inputs['city']);self.trace=[];self.msg_seq=0;self.seen=set();self.commits=[];self.decisions=0
        self.drivers={};self.people={p['id']:p for p in inputs['passengers']};self.passenger_agents={i:Agent(i,'passenger','requesting') for i in self.people}
        self.dispatcher=Agent('dispatcher','dispatcher','available');self.telemetry={};self.pending=set();self.tools={'dispatcher':True,'router':True}
        self.ledger=Ledger({x['id']:x['rating_history'] for x in inputs['drivers']+inputs['passengers']})
        self.initial_ratings={i:rating(h) for i,h in self.ledger.histories.items()}
        self.profiles={}
        for c in inputs['channel_profile']:self.profiles.setdefault(c['channel'],[]).append(c)
        self.profile_starts={}
        for channel,items in self.profiles.items():
            items.sort(key=lambda c:c['from_ms']);self.profile_starts[channel]=[c['from_ms'] for c in items]
        for d in inputs['drivers']:
            self.drivers[d['id']]={'input':d,'agent':Agent(d['id'],'driver'),'node':d['start_node'],'position':None,'busy':None,'offline':bool(d.get('unavailable_until_ms',0)),'movement':None,'idle_since':0,'idle_ms':0,'revenue':0,'distance_m':Fraction(0),'travel_ms':0,'completed':0,'fault_price':None}
        self.orders={o['id']:{**deepcopy(o),'state':'created','version':1,'deadline':o['created_at_ms']+self.people[o['passenger_id']]['max_wait_ms'],'offers':{},'consents':{},'attempts':0,'round':0,'commitment_id':None,'selected':None,'reason':'Заявка ещё не создана','timers':[],'arrived':set(),'tariff_changes':0} for o in inputs['orders']}
        for d in self.drivers.values():
            if d['offline']:d['agent'].state='offline'
        initial={'city':inputs['city'],'drivers':{i:self.driver_view(d) for i,d in self.drivers.items()},'passengers':{i:self.person_view(i) for i in self.people},'orders':{},'stats':{'created':0,'completed':0,'messages':0},'last_message':None,'dispatcher_telemetry':{}}
        self.projection=Projection(initial);self.heartbeat=None
        from .faults import Faults
        self.faults=Faults(self,inputs['faults'])

    def effective_rating(self,who):
        return rating(self.ledger.histories[who]) if self.config['rating_policy']=='dynamic' else self.initial_ratings[who]
    def pos(self,d):
        if d['movement']:return self.router.position(d['movement'],self.e.now)
        return d['position'] or {k:self.router.nodes[d['node']][k] for k in ('x','y')}
    def driver_view(self,d):
        return {'id':d['input']['id'],'role':'driver','state':d['agent'].state,'node':d['node'],'position':self.pos(d),'busy':d['busy'],'vehicle_class':d['input']['vehicle_class'],'rating':f'{float(rating(self.ledger.histories[d["input"]["id"]])):.2f}',
                'knowledge':deepcopy(d['agent'].knowledge),'revenue':rubles(d['revenue']),'cost':rubles(rounded(cost(d['input'],d['distance_m'],d['travel_ms']))),'movement':({k:deepcopy(v) for k,v in d['movement'].items() if k!='_token'} if d['movement'] else None)}
    def person_view(self,i):
        p=self.people[i];a=self.passenger_agents[i];return {'id':i,'role':'passenger','state':a.state,'budget':p['budget'],'rating':f'{float(rating(self.ledger.histories[i])):.2f}','knowledge':deepcopy(a.knowledge)}
    def order_view(self,o):
        keys=('id','passenger_id','origin','destination','created_at_ms','tariff_id','state','version','deadline','attempts','round','commitment_id','reason','driver_id','confirmed_at','boarded_at','completed_at','tariff_changes')
        v={k:o.get(k) for k in keys};v['offers']=[{'id':x['id'],'driver_id':x['driver_id'],'price':rubles(x['price']),'floor':rubles(x['floor']),'eta_ms':x['eta_ms'],'driver_rating':f'{float(x["driver_rating"]):.2f}','status':x.get('status','open'),'round':x.get('round',0)} for x in o['offers'].values()]
        v['price']=rubles(o['price']) if 'price' in o else None
        r=self.router.route(o['origin'],o['destination'])
        if r:
            ref=base_price(o['tariff_id'],r['distance_m'],r['travel_ms']);start=start_price(o['tariff_id'],r['distance_m'],r['travel_ms'],self.effective_rating(o['passenger_id']),self.config['rating_policy']!='off')
            if o.get('_pricing_version')!=o['version']:
                o['_pricing_version']=o['version'];o['_pricing_snapshot']={'base':rubles(ref),'start':rubles(start),'surcharge':rubles(start-ref),'distance_m':r['distance_m'],'travel_ms':r['travel_ms'],'rating_source':str(self.effective_rating(o['passenger_id']))}
            v['pricing']=deepcopy(o['_pricing_snapshot'])
        return v
    def emit(self,kind,reason='',participants=None,details=None,order=None,drivers=(),message=None):
        seq=len(self.trace)+1
        ev={'seq':seq,'event_id':f'E{seq:07}','time_ms':self.e.now,'phase':self.e.phase,'kind':kind,'participants':participants or [],'order_id':order['id'] if order else None,'version':order['version'] if order else None,'reason':reason,'details':deepcopy(details or {})}
        self.trace.append(ev);patch={}
        if order:
            patch['orders']={order['id']:self.order_view(order)};p=order['passenger_id'];patch['passengers']={p:self.person_view(p)}
        if drivers:patch['drivers']={i:self.driver_view(self.drivers[i]) for i in drivers}
        if order:patch['stats']={'created':sum(o.get('released',False) for o in self.orders.values()),'completed':sum(o['state']=='completed' for o in self.orders.values()),'messages':self.msg_seq}
        self.projection.update(seq,self.e.now,patch)
    def decide(self,who,reason,order):
        self.decisions+=1;self.emit('decision',reason,[who],order=order)
    def role(self,who):return 'dispatcher' if who=='dispatcher' else ('driver' if who in self.drivers else 'passenger')
    def profile(self,sender,recipient):
        channel=self.role(sender)+':'+self.role(recipient)
        for key in (channel,'default'):
            items=self.profiles.get(key,[]);index=bisect_right(self.profile_starts.get(key,[]),self.e.now)-1
            if index>=0 and self.e.now<items[index]['to_ms']:return items[index]
        return {'delay_ms':50,'drop':False,'duplicate_count':0,'duplicate_offset_ms':1}
    def send(self,sender,recipient,kind,order=None,payload=None,version=None):
        self.msg_seq+=1;p=self.profile(sender,recipient)
        msg={'id':f'M{self.msg_seq:07}','sender':sender,'recipient':recipient,'kind':kind,'order_id':order['id'] if order else None,'version':version if version is not None else (order['version'] if order else None),'sent_at_ms':self.e.now+1,'deliver_at_ms':self.e.now+1+p['delay_ms'],'correlation_id':order['id'] if order else None,'payload':deepcopy(payload or {})}
        self.faults.message(msg)
        duplicate_copies=msg.pop('_duplicates',0)
        def outgoing():
            self.emit('message_sent',kind,[sender,recipient],details={'message':msg},message=msg)
            if p['drop']:
                self.emit('message_dropped','Потеря в сохранённом профиле канала',[sender,recipient],details={'message_id':msg['id']});return
            self.e.schedule(msg['deliver_at_ms'],2,lambda:self.deliver(msg))
            for n in range(p['duplicate_count']):self.e.schedule(msg['deliver_at_ms']+(n+1)*p['duplicate_offset_ms'],2,lambda:self.deliver(msg))
            for n in range(duplicate_copies):self.e.schedule(msg['deliver_at_ms']+(n+1)*100,2,lambda:self.deliver(msg))
        self.e.schedule(self.e.now+1,2,outgoing)
    def deliver(self,msg):
        o=self.orders.get(msg['order_id']);who=msg['recipient'];key=(who,msg['id'])
        invalid=(o is not None and (msg['version']!=o['version'] or (o['state'] in TERMINAL and msg['kind'] not in {'STATUS','COMPLETE'})))
        if self.protected and (key in self.seen or invalid):
            self.emit('message_rejected','Повтор, устаревшая версия или терминальный заказ',[who],details={'message_id':msg['id'],'kind':msg['kind']});return
        self.seen.add(key)
        self.emit('message_delivered',msg['kind'],[msg['sender'],who],details={'message_id':msg['id'],'kind':msg['kind']},message=msg)
        if who=='dispatcher':self.on_dispatcher(msg,o)
        elif who in self.drivers:self.on_driver(self.drivers[who],msg,o)
        elif who in self.people:self.on_passenger(who,msg,o)
    def timer(self,o,when,phase,callback):
        version=o['version'];token=self.e.schedule(when,phase,lambda:callback() if o['version']==version else None);o['timers'].append(token);return token
    def clear_timers(self,o):
        for token in o['timers']:self.e.cancel_event(token)
        o['timers']=[]
    def active(self):return any(not o.get('released') or o['state'] not in TERMINAL for o in self.orders.values())
    def telemetry_send(self,d):
        if d['offline']:return
        node,observed=d['node'],self.e.now
        movement=d['movement']
        if movement:
            node=movement['route']['origin'];observed=movement['from_ms'];elapsed=self.e.now-observed
            for eid in movement['route']['edge_ids']:
                edge=self.router.edges[eid]
                if elapsed<edge['travel_ms']:break
                elapsed-=edge['travel_ms'];observed+=edge['travel_ms'];node=edge['to']
        self.send(d['input']['id'],'dispatcher','TELEMETRY',payload={'node':node,'busy':d['busy'],'offline':False,'idle_since':d['idle_since'],'observed_at_ms':observed})
    def heartbeat_send(self):
        if not self.active():return
        for d in self.drivers.values():self.telemetry_send(d)
        self.heartbeat=self.e.schedule(self.e.now+self.config['deadlines']['telemetry_interval_ms'],1,self.heartbeat_send)
    def start_order(self,o):
        o['released']=True;o['state']='allocating';o['reason']='Пассажир создал заявку';p=o['passenger_id'];self.passenger_agents[p].state='requesting'
        self.emit('request_created',o['reason'],[p],order=o)
        self.timer(o,o['deadline'],4,lambda:self.finish(o,'expired','Истёк срок ожидания'))
        self.send(p,'dispatcher','REQUEST',o,{'budget':self.people[p]['budget'],'allowed_tariffs':self.people[p]['allowed_tariffs']})
    def request_data(self,o):
        return {'tariff':o['tariff_id'],'passenger_rating':self.effective_rating(o['passenger_id']),'rating_enabled':self.config['rating_policy']!='off'}
    def quote(self,d,o,already_arrived=False):
        trip=self.router.route(o['origin'],o['destination']) if self.tools['router'] else None
        pickup=self.router.route(d['node'],o['origin']) if self.tools['router'] else None
        offer,reason=driver_offer(d['input'],self.request_data(o),{'offline':d['offline'],'busy':d['busy'],'trip_route':trip,'pickup_route':pickup,'driver_rating':self.effective_rating(d['input']['id']),'idle_since':d['idle_since']})
        self.decide(d['input']['id'],reason,o)
        if offer:
            if already_arrived:offer['eta_ms']=0
            if d['fault_price'] is not None:offer['price']=d['fault_price']
            offer.update(id=f'B-{o["id"]}-{o["version"]}-{d["input"]["id"]}-{o["round"]}',round=o['round'],status='open',expires_at=o['deadline'])
            d['agent'].knowledge[o['id']]={'version':o['version'],'tariff':o['tariff_id'],'own_price':rubles(offer['price']),'floor':rubles(offer['floor']),'passenger_rating':str(self.effective_rating(o['passenger_id']))}
        return offer
    def allocate(self,o):
        if o['state'] in TERMINAL:return
        if not self.tools['dispatcher'] or not self.tools['router']:
            self.pending.add(o['id']);self.emit('tool_unavailable','Средство временно недоступно',['dispatcher'],order=o);return
        if self.e.now>=o['deadline']:return self.finish(o,'expired','Истёк срок')
        o['state']='allocating';o['offers']={};o['consents']={};self.pending.discard(o['id'])
        self.decide('dispatcher','Выбран механизм '+self.config['allocation'],o)
        if o.get('candidate_ids'):
            o['state']='provisional_pickup';o['arrived']=set()
            for did in o['candidate_ids']:self.send('dispatcher',did,'PROVISIONAL',o)
            return
        if self.config['allocation']=='auction':
            for did in sorted(self.drivers):self.send('dispatcher',did,'SOLICIT',o)
        close=min(o['deadline'],self.e.now+self.config['deadlines']['allocation_window_ms'])
        self.timer(o,close,3,lambda:self.close_allocation(o))
    def close_allocation(self,o):
        if o['state'] not in {'allocating','awaiting_consent'}:return
        if self.config['allocation']=='central':
            route=self.router.route(o['origin'],o['destination'])
            if not route:return self.finish(o,'cancelled','Маршрут недостижим')
            for did,t in sorted(self.telemetry.items()):
                d=self.drivers[did]
                # Порог не читается: диспетчер использует только публичную наценку и телеметрию.
                pickup=self.router.route(t['node'],o['origin'])
                if t['busy'] or t['offline'] or not pickup or (o['tariff_id']=='comfort' and d['input']['vehicle_class']!='comfort'):continue
                price=start_price(o['tariff_id'],route['distance_m'],route['travel_ms'],self.effective_rating(o['passenger_id']),self.config['rating_policy']!='off')+cents(d['input']['markup'])
                offer={'id':f'C-{o["id"]}-{o["version"]}-{did}','driver_id':did,'price':price,'floor':TARIFFS[o['tariff_id']]['minimum'],'eta_ms':pickup['travel_ms'],'driver_rating':self.effective_rating(did),'idle_since':t['idle_since'],'expires_at':o['deadline'],'status':'open','round':0}
                if d['fault_price'] is not None:offer['price']=d['fault_price']
                o['offers'][did]=offer
        self.choose(o)
    def eligible(self,o,offers):
        minimum=TARIFFS[o['tariff_id']]['minimum']
        candidates=[]
        for offer in offers:
            if offer.get('status') in {'withdrawn','invalidated','rejected'}:continue
            if self.protected and offer['price']<minimum:
                self.emit('protection','Цена ниже минимума тарифа',['dispatcher'],details={'offer_id':offer['id']},order=o);continue
            candidates.append(offer)
        return ranked(candidates,self.people[o['passenger_id']],o['tariff_id'],max(0,o['deadline']-self.e.now),self.config['weights'])
    def choose(self,o):
        candidates=self.eligible(o,list(o['offers'].values()))
        if not candidates:return self.finish(o,'cancelled','Нет приемлемого предложения')
        offer=candidates[0];o['selected']=deepcopy(offer);o['consents']={};o['state']='awaiting_consent';o['reason']='Запрошено согласие обеих сторон';offer['status']='selected'
        self.decide('dispatcher','Минимальная обобщённая стоимость; при равенстве простой и ID',o)
        for who in (offer['driver_id'],o['passenger_id']):self.send('dispatcher',who,'CONSENT_REQUEST',o,{'offer':offer,'tariff':o['tariff_id']})
        self.timer(o,min(o['deadline'],self.e.now+self.config['deadlines']['consent_window_ms']),4,lambda:self.consent_timeout(o))
    def consent_timeout(self,o):
        if o['state']=='awaiting_consent':self.retry(o,'Не получены два согласия')
    def retry(self,o,reason):
        if o['state'] in TERMINAL or o['state']=='in_trip':return
        if o['attempts']>=self.config['deadlines']['max_reassignments']:return self.finish(o,'cancelled',reason+'; предел попыток')
        self.clear_timers(o);o['attempts']+=1;o['version']+=1;o['offers']={};o['selected']=None;o['consents']={};o['state']='allocating'
        self.emit('reassigned',reason,['dispatcher'],order=o)
        self.timer(o,o['deadline'],4,lambda:self.finish(o,'expired','Истёк срок ожидания'))
        self.allocate(o)
    def on_dispatcher(self,m,o):
        kind=m['kind'];payload=m['payload'];sender=m['sender']
        if not self.tools['dispatcher']:
            if o:
                self.pending.add(o['id'])
                if kind=='REQUEST':self.emit('tool_unavailable','Диспетчер не отвечает',['dispatcher'],order=o)
            return
        if kind=='TELEMETRY':
            if sender not in self.drivers:
                self.emit('message_rejected','Телеметрия разрешена только водителю',[sender]);return
            if payload['node'] not in self.router.nodes:return
            if self.protected:
                previous=self.telemetry.get(sender,{'node':self.drivers[sender]['input']['start_node'],'observed_at_ms':0})
                route=self.router.route(previous['node'],payload['node'])
                elapsed=payload['observed_at_ms']-previous['observed_at_ms']
                if elapsed<0 or route is None or route['travel_ms']>elapsed:
                    self.emit('message_rejected','Позиция не достижима по последнему наблюдению',[sender]);return
            self.telemetry[sender]=deepcopy(payload)
            self.projection.update(len(self.trace),self.e.now,{'dispatcher_telemetry':{sender:deepcopy(payload)}},checkpoint=False)
            return
        if not o:return
        if kind=='REQUEST':self.dispatcher.knowledge[o['id']]=payload;self.allocate(o)
        elif kind=='OFFER' and o['state'] in {'allocating','negotiating'}:
            offer=deepcopy(payload['offer'])
            if self.protected and sender in self.telemetry:
                t=self.telemetry[sender];route=self.router.route(t['node'],o['origin'])
                bound=max(0,route['travel_ms']-(self.e.now-t['observed_at_ms'])) if route else 0
                if not o.get('candidate_ids') and offer['eta_ms']<bound:
                    self.emit('message_rejected','Заявленное время подачи противоречит наблюдениям',[sender],order=o);return
            o['offers'][sender]=offer
            self.emit('offer','Обязывающее предложение водителя',[sender],order=o,drivers=[sender])
            self.send('dispatcher',o['passenger_id'],'OFFER',o,{'offer':offer})
            if o.get('candidate_ids'):
                for did in o['candidate_ids']:
                    if did!=sender:self.send('dispatcher',did,'PUBLIC_OFFER',o,{'driver_id':sender,'price':rubles(offer['price'])})
                if self.config['conflict_policy']=='first_acceptable' and self.eligible(o,[offer]):self.choose(o)
        elif kind=='DECLINE' and o['state']=='awaiting_consent':
            if o['selected']:
                rejected=o['selected']['driver_id']
                if rejected in o['offers']:o['offers'][rejected]['status']='rejected'
            if self.eligible(o,list(o['offers'].values())):self.choose(o)
            else:self.retry(o,payload.get('reason','Отказ участника'))
        elif kind=='CONSENT' and o['state']=='awaiting_consent':
            selected=o['selected'];expected={selected['driver_id'],o['passenger_id']}
            if sender not in expected or payload.get('price')!=selected['price'] or payload.get('tariff')!=o['tariff_id']:
                self.emit('message_rejected','Согласие не соответствует условиям',[sender],order=o);return
            o['consents'][sender]=deepcopy(payload)
            self.emit('consent','Участник подтвердил цену, тариф и версию',[sender],order=o)
            if expected<=o['consents'].keys():self.commit(o,selected)
        elif kind=='ARRIVED' and self.current_commit(o,payload.get('commitment_id')):
            self.send('dispatcher',o['passenger_id'],'BOARD_REQUEST',o,{'commitment_id':o['commitment_id']})
        elif kind=='BOARD_CONFIRM':self.board(o,payload.get('commitment_id'))
        elif kind=='COMPLETE':self.complete(o,payload.get('commitment_id'),sender)
        elif kind=='PROVISIONAL_ARRIVED' and o['state']=='provisional_pickup':
            o['arrived'].add(sender)
            if set(o['candidate_ids'])<=o['arrived']:self.start_round(o)
        elif kind=='COUNTER_REPLY' and o['state']=='negotiating' and payload.get('round')==o['round']:
            offer=o['offers'].get(sender)
            if offer and payload.get('accepted') and payload['price']<=offer['price']:
                offer['price']=payload['price'];offer['id']+='-counter';offer['status']='counter_accepted'
            self.emit('counter_reply','Встречная цена принята' if payload.get('accepted') else 'Встречная цена отклонена',[sender],details=payload,order=o)
        elif kind=='TARIFF_REPLY' and o['state']=='negotiating':
            if payload.get('accepted') and payload.get('next_version')==o['version']+1 and o.get('tariff_proposal'):
                proposal=o.pop('tariff_proposal');self.clear_timers(o);o['version']+=1;o['tariff_id']=proposal;o['tariff_changes']+=1;o['offers']={};o['consents']={}
                self.emit('tariff_changed','Стороны согласовали новый тариф; старые предложения аннулированы',[sender,o['passenger_id']],order=o)
                self.timer(o,o['deadline'],4,lambda:self.finish(o,'expired','Истёк срок ожидания'))
                if o['round']>=3:self.finish(o,'cancelled','Смена тарифа исчерпала раунды')
                else:self.start_round(o)
    def on_driver(self,d,m,o):
        kind=m['kind'];who=d['input']['id'];p=m['payload']
        if self.protected and kind in {'CONFIRM','REVOKE','SOLICIT','CONSENT_REQUEST','PROVISIONAL','ROUND_REQUEST','COUNTER','TARIFF_PROPOSE'} and m['sender']!='dispatcher':
            self.emit('message_rejected','Отправитель не имеет полномочий',[who],order=o);return
        if d['offline']:return
        if kind=='PUBLIC_OFFER':
            d['agent'].knowledge['public_offer']=p;return
        if not o:return
        if kind in {'SOLICIT','ROUND_REQUEST'}:
            offer=self.quote(d,o,already_arrived=kind=='ROUND_REQUEST')
            if offer:
                previous=o['offers'].get(who)
                if kind=='ROUND_REQUEST' and previous:
                    offer['price']=next_price(d['input'],previous);offer['floor']=previous['floor']
                d['agent'].state='negotiating' if kind=='ROUND_REQUEST' else 'offering'
                self.send(who,'dispatcher','OFFER',o,{'offer':offer})
        elif kind=='PROVISIONAL':
            if d['busy']:return
            route=self.router.route(d['node'],o['origin'])
            if route:
                d['agent'].state='provisional_to_pickup'
                self.move(d,route,o,lambda:self.send(who,'dispatcher','PROVISIONAL_ARRIVED',o))
        elif kind=='COUNTER':
            offer=o['offers'].get(who);accepted=bool(offer and driver_counter(offer,p['price']) and not d['busy'])
            self.decide(who,'Принять контрцену' if accepted else 'Контрцена ниже порога либо условия недопустимы',o)
            self.send(who,'dispatcher','COUNTER_REPLY',o,{'accepted':accepted,'price':p['price'],'round':p['round']})
        elif kind=='TARIFF_PROPOSE':
            compatible=p['tariff']=='economy' or d['input']['vehicle_class']=='comfort'
            self.send(who,'dispatcher','TARIFF_REPLY',o,{'accepted':compatible and not d['busy'],'next_version':p['next_version']})
        elif kind=='CONSENT_REQUEST':
            offer=p['offer'];own=self.quote(d,o,already_arrived=bool(o.get('candidate_ids')))
            ok=own is not None and (offer['price']>=own['floor'] or d['fault_price'] is not None)
            self.send(who,'dispatcher','CONSENT' if ok else 'DECLINE',o,{'price':offer['price'],'tariff':o['tariff_id'],'reason':'Индивидуальный порог либо занятость'})
        elif kind=='CONFIRM':
            if not self.current_commit(o,p.get('commitment_id')):return
            if d['movement'] and d['movement'].get('order_id')==o['id']:return
            if d['busy']!=o['id']:return
            route=self.router.route(d['node'],o['origin']);d['agent'].state='to_pickup';o['state']='pickup'
            self.move(d,route,o,lambda:self.send(who,'dispatcher','ARRIVED',o,{'commitment_id':p['commitment_id']}))
        elif kind=='REVOKE':d['agent'].knowledge['revoked']=p
    def on_passenger(self,who,m,o):
        if not o:return
        a=self.passenger_agents[who];p=m['payload']
        if m['kind']=='OFFER':
            a.knowledge.setdefault('offers',{})[p['offer']['driver_id']]=rubles(p['offer']['price'])
        elif m['kind']=='CONSENT_REQUEST':
            ok=passenger_accept(self.people[who],p['offer'],p['tariff'],max(0,o['deadline']-self.e.now))
            a.state='evaluating';self.decide(who,'Условия приемлемы' if ok else 'Нарушен бюджет, срок или рейтинг',o)
            self.send(who,'dispatcher','CONSENT' if ok else 'DECLINE',o,{'price':p['offer']['price'],'tariff':p['tariff'],'reason':'Ограничения пассажира'})
        elif m['kind']=='CONFIRM':a.state='waiting';a.knowledge['commitment_id']=p['commitment_id']
        elif m['kind']=='BOARD_REQUEST':
            if a.state!='onboard':self.send(who,'dispatcher','BOARD_CONFIRM',o,{'commitment_id':p['commitment_id']})
    def current_commit(self,o,cid):
        return bool(cid and cid==o['commitment_id'] and any(c['id']==cid and c['version']==o['version'] and c['state'] in {'confirmed','boarded'} for c in self.commits))
    def commit(self,o,offer,forced=False):
        if not all(self.tools.values()):
            self.pending.add(o['id']);self.emit('tool_unavailable','Новые обязательства при отказе средства не подтверждаются',['dispatcher'],order=o);return
        did=offer['driver_id'];d=self.drivers[did];existing=[c for c in self.commits if c['order_id']==o['id'] and c['state'] in {'confirmed','boarded'}]
        expected={did,o['passenger_id']}
        invalid_consent=not expected<=o['consents'].keys() or any(v.get('price')!=offer['price'] or v.get('tariff')!=o['tariff_id'] for v in o['consents'].values())
        if self.protected and (invalid_consent or existing or d['busy'] or self.e.now>o['deadline'] or o['state'] in TERMINAL or not self.tools['dispatcher']):
            self.emit('protection','Атомарная проверка отклонила противоречивое назначение',['dispatcher',did],order=o);return
        cid=f'K{o["id"]}-{o["version"]}-{len(self.commits)+1}'
        c={'id':cid,'order_id':o['id'],'driver_id':did,'passenger_id':o['passenger_id'],'version':o['version'],'tariff':o['tariff_id'],'price':offer['price'],'state':'confirmed','consents':sorted(o['consents'])}
        self.commits.append(c)
        if existing or d['busy']:self.emit('violation','Противоречивое логическое назначение',['dispatcher',did],details={'invariant':'I1/I2'},order=o)
        if offer['price']<TARIFFS[o['tariff_id']]['minimum']:self.emit('violation','Согласованная цена ниже тарифного минимума',[did],details={'invariant':'tariff_minimum'},order=o)
        self.clear_timers(o);o.update(commitment_id=cid,driver_id=did,price=offer['price'],confirmed_at=self.e.now,state='assigned',reason='Получены два согласия')
        self.leave_idle(d);d['busy']=o['id'];d['agent'].state='reserved';self.passenger_agents[o['passenger_id']].state='waiting'
        self.emit('confirmed','Цена, тариф, версия и исполнитель зафиксированы',['dispatcher',did,o['passenger_id']],details={'commitment':c},order=o,drivers=[did])
        for who in (did,o['passenger_id']):self.send('dispatcher',who,'CONFIRM',o,{'commitment_id':cid,'price':offer['price'],'tariff':o['tariff_id']})
        pickup_deadline=min(o['deadline'],self.e.now+offer['eta_ms']+self.config['deadlines']['pickup_grace_ms'])
        self.timer(o,pickup_deadline,4,lambda:self.pickup_timeout(o,cid))
        if not forced:self.faults.after_confirm(o,did)
        self.telemetry_send(d)
    def pickup_timeout(self,o,cid):
        if o['state'] not in {'assigned','pickup'} or not self.current_commit(o,cid):return
        if not self.protected:return self.timer(o,o['deadline'],4,lambda:self.finish(o,'expired','Водитель не подал машину')) if self.e.now<o['deadline'] else self.finish(o,'expired','Водитель не подал машину')
        self.revoke(o,'Тайм-аут подачи');self.retry(o,'Тайм-аут подачи')
    def leave_idle(self,d):
        if d['busy'] is None and not d['offline'] and d['movement'] is None:
            d['idle_ms']+=self.e.now-d['idle_since'];d['idle_since']=self.e.now
    def stop_move(self,d):
        movement=d['movement']
        if not movement:return
        self.e.cancel_event(movement.get('_token'))
        elapsed=max(0,min(self.e.now-movement['from_ms'],movement['route']['travel_ms']));remaining=elapsed;distance=Fraction(0)
        for eid in movement['route']['edge_ids']:
            edge=self.router.edges[eid];part=min(remaining,edge['travel_ms']);distance+=Fraction(edge['distance_m']*part,edge['travel_ms']);remaining-=part
            if remaining<=0:break
        d['distance_m']+=distance;d['travel_ms']+=elapsed;d['position']=self.router.position(movement,self.e.now)
        d['movement']=None
        if d['busy'] is None:d['idle_since']=self.e.now
    def move(self,d,route,o,callback):
        if not route:return self.finish(o,'failed','Маршрут недостижим')
        self.leave_idle(d);who=d['input']['id'];start=self.e.now
        movement={'agent_id':who,'order_id':o['id'],'from_ms':start,'to_ms':start+route['travel_ms'],'route':route}
        def arrived():
            if d['offline'] or d['movement'] is not movement:return
            d['distance_m']+=route['distance_m'];d['travel_ms']+=route['travel_ms'];d['node']=route['destination'];d['position']=None;d['movement']=None
            if d['busy'] is None:d['idle_since']=self.e.now
            self.emit('movement_finished','Достигнута точка маршрута',[who],order=o,drivers=[who]);callback()
        movement['_token']=self.e.schedule(start+max(1,route['travel_ms']),1,arrived);d['movement']=movement
        self.projection.movements.append({k:deepcopy(v) for k,v in movement.items() if k!='_token'})
        self.emit('movement_started','Начато движение по сохранённому маршруту',[who],order=o,drivers=[who])
    def board(self,o,cid):
        if not self.current_commit(o,cid) or o['state'] not in {'pickup','assigned'}:return
        d=self.drivers[o['driver_id']];p=self.passenger_agents[o['passenger_id']]
        if d['busy']!=o['id'] or d['offline'] or d['node']!=o['origin'] or d['movement'] or p.state=='onboard':
            self.emit('protection','Физическая посадка не разрешена',['dispatcher'],order=o);return
        self.clear_timers(o);o['state']='in_trip';o['boarded_at']=self.e.now;p.state='onboard';p.knowledge['driver_id']=o['driver_id'];d['agent'].state='carrying'
        for c in self.commits:
            if c['id']==cid:c['state']='boarded'
        self.emit('boarded','Пассажир подтвердил посадку',[p.id,o['driver_id']],order=o,drivers=[o['driver_id']])
        route=self.router.route(o['origin'],o['destination'])
        self.move(d,route,o,lambda:self.send(o['driver_id'],'dispatcher','COMPLETE',o,{'commitment_id':cid}))
    def complete(self,o,cid,sender):
        if o['state']!='in_trip' or sender!=o['driver_id'] or not self.current_commit(o,cid):return
        d=self.drivers[sender]
        if d['node']!=o['destination'] or d['movement'] or d['busy']!=o['id']:return
        d['revenue']+=o['price'];d['completed']+=1;o['completed_at']=self.e.now
        self.ledger.authorize(cid,(sender,o['passenger_id']),5,'completed')
        for who in (sender,o['passenger_id']):self.ledger.record(who,cid,5,'completed','environment')
        self.finish(o,'completed','Поездка выполнена по согласованной цене')
    def revoke(self,o,reason):
        cid=o['commitment_id'];did=o.get('driver_id')
        for c in self.commits:
            if c['id']==cid:c['state']='revoked'
        if did:
            d=self.drivers[did]
            if d['busy']==o['id']:
                self.stop_move(d);d['busy']=None;d['agent'].state='offline' if d['offline'] else 'idle';d['idle_since']=self.e.now
            self.send('dispatcher',did,'REVOKE',o,{'commitment_id':cid,'reason':reason})
            if d['offline']:
                self.ledger.authorize(cid,[did],1,'no_show');self.ledger.record(did,cid,1,'no_show','environment')
        o['commitment_id']=None
    def finish(self,o,state,reason):
        if o['state'] in TERMINAL:return
        was_in_trip=o['state']=='in_trip';self.clear_timers(o);o['state']=state;o['reason']=reason
        cid=o['commitment_id']
        for c in self.commits:
            if c['order_id']==o['id'] and c['state'] in {'confirmed','boarded'}:c['state']='completed' if state=='completed' else 'failed'
        touched=[]
        for did,d in self.drivers.items():
            if d['busy']==o['id']:
                if was_in_trip and state!='completed':self.stop_move(d);d['offline']=True
                d['busy']=None;d['agent'].state='offline' if d['offline'] else 'idle';d['idle_since']=self.e.now;touched.append(did)
            elif did in o.get('candidate_ids',[]) and d['busy'] is None and d['movement'] is None:
                self.leave_idle(d);d['agent'].state='idle';d['idle_since']=self.e.now;touched.append(did)
        self.passenger_agents[o['passenger_id']].state='arrived' if state=='completed' else state
        self.emit('order_'+state,reason,[o['passenger_id']],order=o,drivers=touched)
        if not self.active():self.e.cancel_event(self.heartbeat)
    def start_round(self,o):
        if o['state'] in TERMINAL:return
        o['state']='negotiating';o['round']+=1
        if o['round']>3:return self.finish(o,'cancelled','Исчерпаны раунды')
        self.passenger_agents[o['passenger_id']].state='negotiating'
        self.emit('round_started','Раунд '+str(o['round']),o.get('candidate_ids',[])+[o['passenger_id']],order=o)
        self.faults.negotiation(o)
        for did in o['candidate_ids']:self.send('dispatcher',did,'ROUND_REQUEST',o)
        if self.config['conflict_policy']=='first_acceptable':return
        length=self.config['deadlines']['round_ms'];o['round_started_at']=self.e.now
        self.timer(o,min(o['deadline'],self.e.now+length//2),3,lambda:self.counter_round(o))
        self.timer(o,min(o['deadline'],self.e.now+length),3,lambda:self.close_round(o))
    def counter_round(self,o):
        if o['state']!='negotiating':return
        offers=list(o['offers'].values());p=self.people[o['passenger_id']]
        if offers and all(x['price']>cents(p['budget']) for x in offers) and o['tariff_id']=='comfort' and 'economy' in p['allowed_tariffs']:
            o['tariff_proposal']='economy';self.decide(o['passenger_id'],'Предложить переход на Эконом в пределах бюджета',o)
            self.emit('tariff_proposed','Пассажир явно согласился на Эконом',[o['passenger_id']],order=o)
            for did in o['candidate_ids']:self.send('dispatcher',did,'TARIFF_PROPOSE',o,{'tariff':'economy','next_version':o['version']+1})
            return
        price=counterprice(p,offers,o['tariff_id'])
        if price is not None:
            self.decide(o['passenger_id'],'Встречная цена в пределах бюджета',o)
            self.emit('counter_proposed','Встречная цена пассажира',[o['passenger_id']],details={'price':rubles(price)},order=o)
            for did in sorted(o['offers']):self.send('dispatcher',did,'COUNTER',o,{'price':price,'round':o['round']})
    def close_round(self,o):
        if o['state']!='negotiating':return
        if self.eligible(o,list(o['offers'].values())):return self.choose(o)
        current=tuple((i,x['price']) for i,x in sorted(o['offers'].items()))
        if o.get('last_round_prices')==current:return self.finish(o,'cancelled','NO_PROGRESS: цены не изменились')
        o['last_round_prices']=current
        if o['round']>=3:return self.finish(o,'cancelled','NO_AGREEMENT: нет приемлемых условий')
        self.start_round(o)
    def run(self):
        self.faults.schedule()
        for did,d in self.drivers.items():
            if d['input'].get('unavailable_until_ms'):
                def restore(d=d):
                    d['offline']=False;d['agent'].state='idle';d['idle_since']=self.e.now
                    self.emit('driver_available','Восстановлена доступность по входному расписанию',[d['input']['id']],drivers=[d['input']['id']]);self.telemetry_send(d)
                self.e.schedule(d['input']['unavailable_until_ms'],0,restore)
        for o in self.orders.values():self.e.schedule(o['created_at_ms'],1,lambda o=o:self.start_order(o))
        if self.orders:self.e.schedule(0,1,self.heartbeat_send)
        self.e.run()
        for d in self.drivers.values():
            self.stop_move(d)
            self.leave_idle(d)
        from .metrics import measure
        if self.e.termination!='completed':self.emit('simulation_stopped',self.e.termination,drivers=list(self.drivers))
        metrics,orders,drivers=measure(self)
        return Run(self.inputs,self.config,self.trace,orders,drivers,metrics,self.projection.result(),self.e.termination,self.faults.results)

def simulate(inputs,cancel=None):return Simulation(inputs,cancel).run()
