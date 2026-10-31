"""Внешние контролируемые воздействия; агентам этот контроллер недоступен."""
from copy import deepcopy
from .pricing import cents
from .domain import TERMINAL
class Faults:
    def __init__(self,sim,items):
        self.s=sim;self.results=[{**deepcopy(f),'status':'not_triggered','activated_at_ms':None,'resolved_target':None} for f in items]
    def activate(self,f,target):
        if f['status']!='not_triggered':return False
        f.update(status='activated',activated_at_ms=self.s.e.now,resolved_target=target)
        self.s.emit('fault_activated',f['type'],[target],details={'fault_id':f['id'],'type':f['type'],'parameters':f['parameters']});return True
    def schedule(self):
        for f in self.results:
            if f['trigger']['kind']=='time':self.s.e.schedule(f['trigger']['time_ms'],0,lambda f=f:self.apply(f))
    def apply(self,f,o=None,did=None):
        s=self.s;target=f['target'] if f['target']!='first_matching' else (did or next(iter(s.drivers),'dispatcher'))
        if not self.activate(f,target):return
        p=f['parameters'];kind=f['type']
        if (kind=='F1' or (kind=='F5' and p.get('mode')=='breach')) and target in s.drivers:
            d=s.drivers[target];s.stop_move(d);d['offline']=True;d['agent'].state='offline'
            s.emit('driver_unavailable','Водитель прекратил ответы',[target],order=o,drivers=[target])
            if o and o['state']=='in_trip':
                s.ledger.authorize(o['commitment_id'],[target],1,'breach');s.ledger.record(target,o['commitment_id'],1,'breach','environment');s.finish(o,'failed','Отказ водителя после посадки; пассажир остаётся в фактической позиции')
        elif kind=='F2' and target in s.drivers:
            d=s.drivers[target]
            if p.get('field','price')=='price':d['fault_price']=cents(p.get('replacement','99.00'))
            else:d['false_claim']={'field':p.get('field'),'replacement':p.get('replacement',0)}
        elif kind=='F4' and o:
            s.emit('violation_attempt','Попытка несовместимого назначения или передачи полномочий',['dispatcher'],order=o)
            if p.get('mode')=='unauthorized':s.send(o['passenger_id'],did,'CONFIRM',o,{'commitment_id':o['commitment_id']});return
            other=next((i for i in s.drivers if i!=did),None)
            if other:
                offer=deepcopy(o['selected']);offer['driver_id']=other
                s.emit('violation_attempt','Противоречивое назначение от неисправного диспетчера',['dispatcher',other],order=o)
                s.commit(o,offer,forced=True)
        elif kind=='F6':
            tool=p.get('tool','dispatcher');s.tools[tool]=False
            s.emit('tool_failed','Недоступно средство '+tool,[target])
            def restore():
                s.tools[tool]=True;s.emit('tool_restored','Средство восстановлено',[target])
                if s.protected:
                    for d in s.drivers.values():s.telemetry_send(d)
                    for oid in sorted(s.pending.copy()):
                        if s.orders[oid]['state'] not in TERMINAL:s.allocate(s.orders[oid])
            s.e.schedule(p.get('unavailable_to_ms',20000),0,restore)
        elif kind=='F7':
            accepted=s.ledger.record(target,'forged',p.get('forged_value',5),'completed',p.get('asserted_source','agent'))
            s.emit('protection' if not accepted else 'violation','Поддельное репутационное событие отклонено проверенным реестром',[target],details={'fault_id':f['id']})
    def after_confirm(self,o,did):
        for f in self.results:
            if f['trigger']['kind']=='after_confirm' and f['status']=='not_triggered':
                delay=f['parameters'].get('delay_ms',100)
                self.s.e.schedule(self.s.e.now+max(1,delay),0,lambda f=f:self.apply(f,o,did))
    def message(self,msg):
        for f in self.results:
            if f['type']=='F3' and f['status']=='not_triggered' and f['trigger']['kind']=='message' and msg['kind']==f['trigger'].get('message_kind','CONFIRM'):
                if self.activate(f,msg['recipient']):
                    if f['parameters'].get('mode')=='delay':msg['deliver_at_ms']+=f['parameters'].get('delay_ms',10000)
                    else:msg['_duplicates']=f['parameters'].get('count',2)
            if f['type']=='F2' and f['status']=='activated' and msg['sender']==f['resolved_target']:
                p=f['parameters'];field=p.get('field')
                if field=='position' and msg['kind']=='TELEMETRY':msg['payload']['node']=p.get('replacement','N44')
                if field=='eta' and msg['kind']=='OFFER':msg['payload']['offer']['eta_ms']=p.get('replacement',0)
    def negotiation(self,o):
        for f in self.results:
            if f['type']!='F5' or f['status']!='not_triggered' or f['trigger']['kind']!='negotiation':continue
            target=o['candidate_ids'][0]
            if not self.activate(f,target):continue
            counter=[0]
            def loop():
                counter[0]+=1
                if self.s.protected and (counter[0]>3 or o['state'] in TERMINAL or o['state']!='negotiating'):
                    self.s.emit('protection','Изменённая цель ограничена состоянием и числом действий',[target],order=o);return
                self.s.decide(target,'Изменённая цель: повторная передача заявки',o)
                self.s.send(target,'dispatcher','REDELEGATE',o,{'attempt':counter[0]})
                self.s.e.schedule(self.s.e.now+1000,1,loop)
            self.s.e.schedule(self.s.e.now+1,1,loop)
