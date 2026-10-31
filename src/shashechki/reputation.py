"""Проверенная история отделена от утверждений агентов."""
from copy import deepcopy
from fractions import Fraction
def rating(history):
    return (Fraction(45,2)+sum(Fraction(str(x['value'])) for x in history))/(5+len(history))
class Ledger:
    def __init__(self,histories):
        self.histories=deepcopy(histories);self.seen=set();self.authorized={}
    def authorize(self,commitment,subjects,value,cause):
        for subject in subjects:self.authorized[(subject,commitment,cause)]=value
    def record(self,subject,commitment,value,cause,source):
        key=(subject,commitment)
        if source!='environment' or self.authorized.get((subject,commitment,cause))!=value or cause not in {'completed','no_show','breach'} or value not in {1,5} or key in self.seen:
            return False
        self.seen.add(key)
        self.histories[subject].append({'id':f'R-{subject}-{commitment}','value':value,'cause':cause,
            'commitment_id':commitment,'source_event_id':commitment,'origin':'environment'})
        return True
