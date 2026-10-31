"""Последовательная очередь: время, фаза, устойчивый номер."""
import heapq
class ModelLimit(Exception):pass
class Engine:
    def __init__(self,horizon_ms=86400000,max_events=1000000,max_pending_events=100000,cancel=None):
        self.now=0;self.phase=-1;self.sequence=0;self.queue=[];self.processed=0
        self.horizon=horizon_ms;self.max_events=max_events;self.max_pending=max_pending_events
        self.cancel=cancel or (lambda:False);self.termination='completed'
    def schedule(self,time_ms,phase,callback):
        if time_ms<self.now or (time_ms==self.now and phase<self.phase):raise ValueError('Событие запланировано в прошлое')
        if len(self.queue)>=self.max_pending:raise ModelLimit()
        self.sequence+=1;token=[True];heapq.heappush(self.queue,(time_ms,phase,self.sequence,(token,callback)));return token
    def run(self):
        try:
            while self.queue:
                if self.cancel():self.termination='cancelled';break
                if self.processed>=self.max_events:self.termination='limit_reached';break
                time,phase,_,item=heapq.heappop(self.queue)
                token,callback=item
                if not token[0]:continue
                token[0]=False
                if time>self.horizon:self.now=self.horizon;self.termination='horizon_reached';break
                self.now,self.phase=time,phase;self.processed+=1;callback()
        except ModelLimit:self.termination='limit_reached'

    def cancel_event(self,token):
        if token:token[0]=False
