"""Сохранённые присваивания представления; никакой предметной логики в браузере."""
from copy import deepcopy
class Projection:
    def __init__(self,initial):
        self.state=deepcopy(initial);self.initial=deepcopy(initial);self.changes=[];self.checkpoints=[];self.movements=[];self.semantic_changes=0
    def update(self,seq,time_ms,patch,checkpoint=True):
        for key,items in patch.items():
            if key in {'drivers','passengers','orders','dispatcher_telemetry'}:self.state[key].update(deepcopy(items))
            else:self.state[key]=deepcopy(items)
        if patch:self.changes.append({'seq':seq,'time_ms':time_ms,'assignments':deepcopy(patch)})
        if patch and checkpoint:
            self.semantic_changes+=1
            if self.semantic_changes%100==0:self.checkpoints.append({'seq':seq,'change_index':len(self.changes),'state':deepcopy(self.state)})
    def result(self):
        return {'schema_version':'1.0','initial_snapshot':self.initial,'checkpoints':self.checkpoints,
                'changes':self.changes,'movements':self.movements}
