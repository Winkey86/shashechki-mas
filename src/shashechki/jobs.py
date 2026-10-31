"""Один worker, две ожидающие задачи и устойчивый реестр request_id."""
from pathlib import Path
from copy import deepcopy
import threading,queue,uuid,traceback
from .domain import InputError,ID_PATTERN
from .validation import fields,require,config,load,validate
from .artifacts import canonical,digest,read_json,write_json,execute,export_result,verify
from .experiments import load_experiment,run_series

class JobError(Exception):
    def __init__(self,code,message,status=409,retryable=False):self.code=code;self.message=message;self.status=status;self.retryable=retryable

class Jobs:
    def __init__(self,root,scenarios,registry):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.scenarios=Path(scenarios);self.registry=Path(registry);self.registry.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.queue=queue.Queue(maxsize=2);self.records={};self.requests={};self.payloads={};self.cancel_flags={};self.stopping=threading.Event()
        if self.registry.exists():
            self.records=read_json(self.registry)
            for ident,record in self.records.items():
                self.requests[record['request_id']]=ident
                if record['state'] in {'queued','running','cancelling'}:record.update(state='failed',error={'code':'INTERRUPTED','message':'Предыдущее выполнение было прервано','retryable':True,'field_errors':[]})
        self.persist();self.thread=threading.Thread(target=self.worker,name='shashechki-worker',daemon=True);self.thread.start()
    def persist(self):write_json(self.registry,self.records)
    def public(self,record):return deepcopy({k:v for k,v in record.items() if k not in {'body_hash','body'}})
    def get(self,ident):
        with self.lock:
            if ident not in self.records:raise JobError('NOT_FOUND','Задание не найдено',404)
            return self.public(self.records[ident])
    def result_path(self,ident):
        if not isinstance(ident,str) or not ID_PATTERN.fullmatch(ident):raise JobError('NOT_FOUND','Результат не найден',404)
        direct=self.root/ident
        if direct.is_dir() and ident.startswith(('run-','series-')):return direct
        for series in sorted(self.root.glob('series-*')):
            candidate=series/'runs'/ident
            if candidate.is_dir():return candidate
        raise JobError('NOT_FOUND','Результат не найден',404)
    def scenarios_catalog(self):
        rows=[]
        overrides={'allocation':['central','auction'],'conflict_policy':['first_acceptable','negotiation'],'rating_policy':['off','fixed','dynamic'],'protection_profile':['baseline','protected'],'tariff_id':['economy','comfort'],'passenger_history_score':[1,2,3,4,5],'budget':{'type':'money'}}
        for p in sorted(self.scenarios.glob('*.json')):
            s=load(p);rows.append({'id':s['scenario_id'],'title':s.get('title',s['scenario_id']),'description':s.get('description',''),'kind':'run','allowed_overrides':overrides,'config':s['config']})
        for p in sorted((self.scenarios/'series').glob('*.json')):
            e=load_experiment(p);rows.append({'id':e['experiment_id'],'title':e.get('title',e['experiment_id']),'description':str(len(e['conditions'])*len(e['seeds'])*2)+' прогонов','kind':'series','allowed_overrides':{}})
        return rows
    def prepare(self,body):
        fields(body,('schema_version','request_id','kind'),('scenario_id','overrides','experiment_id','result_id','archive_name'))
        require(body['schema_version']=='1.0','Неподдерживаемая схема','schema_version')
        require(isinstance(body['request_id'],str) and bool(ID_PATTERN.fullmatch(body['request_id'])),'Неверный request_id','request_id')
        kind=body['kind'];specific={'run':{'scenario_id','overrides'},'series':{'experiment_id'},'export':{'result_id','archive_name'}}
        require(isinstance(kind,str) and kind in specific,'Неизвестный тип задания','kind')
        require(set(body)-{'schema_version','request_id','kind'}<=specific[kind],'Поля не соответствуют типу задания')
        require((specific[kind]-{'overrides'})<=body.keys(),'Отсутствуют обязательные поля задания')
        if kind=='run':
            ident=body.get('scenario_id');require(isinstance(ident,str) and bool(ID_PATTERN.fullmatch(ident)),'Неверный сценарий','scenario_id')
            path=self.scenarios/(ident+'.json')
            if not path.is_file():raise JobError('NOT_FOUND','Сценарий не найден',404)
            s=load(path);override=body.get('overrides',{});allowed={'allocation','conflict_policy','rating_policy','protection_profile','tariff_id','budget','passenger_history_score'}
            fields(override,(),allowed,'overrides')
            s['config']=config({**s['config'],**{k:v for k,v in override.items() if k in {'allocation','conflict_policy','rating_policy','protection_profile'}}})
            if 'tariff_id' in override:
                for o in s['orders']:o['tariff_id']=override['tariff_id']
            if 'budget' in override:
                for p in s['passengers']:p['budget']=override['budget']
            if 'passenger_history_score' in override:
                score=override['passenger_history_score'];require(type(score) is int and 1<=score<=5,'Оценка вне диапазона','overrides.passenger_history_score')
                for p in s['passengers']:
                    for h in p['rating_history']:h['value']=score
            return validate(s)
        if kind=='series':
            ident=body.get('experiment_id');require(isinstance(ident,str) and bool(ID_PATTERN.fullmatch(ident)),'Неверное исследование','experiment_id')
            path=self.scenarios/'series'/(ident+'.json')
            if not path.is_file():raise JobError('NOT_FOUND','Исследование не найдено',404)
            return load_experiment(path)
        source=self.result_path(body.get('result_id'));verify(source)
        name=body.get('archive_name');require(isinstance(name,str) and bool(ID_PATTERN.fullmatch(name[:-4])) and name.endswith('.zip'),'Недопустимое имя архива','archive_name')
        exports=self.root/'exports';exports.mkdir(exist_ok=True);destination=exports/name
        if destination.exists():raise JobError('ARTIFACT_EXISTS','Архив с таким именем уже существует')
        return (source,destination)
    def submit(self,body):
        body_hash=digest(body)
        with self.lock:
            request_id=body.get('request_id') if isinstance(body,dict) else None
            existing=self.requests.get(request_id) if isinstance(request_id,str) else None
            if existing:
                record=self.records[existing]
                if record['body_hash']!=body_hash:raise JobError('REQUEST_ID_CONFLICT','request_id уже связан с другим содержимым')
                return self.public(record),False
            payload=self.prepare(body)
            if body['kind']=='export' and any(r['kind']=='export' and r['state'] in {'queued','running','cancelling'} and r['body'].get('archive_name')==body['archive_name'] for r in self.records.values()):raise JobError('ARTIFACT_EXISTS','Это имя архива уже зарезервировано')
            ident='job-'+uuid.uuid4().hex[:20];total=len(payload['conditions'])*len(payload['seeds'])*2 if body['kind']=='series' else 1
            record={'job_id':ident,'request_id':body['request_id'],'kind':body['kind'],'state':'queued','phase':'В очереди','completed_runs':0,'total_runs':total,'current_result_id':None,'result_ids':[],'error':None,'body_hash':body_hash,'body':deepcopy(body)}
            self.records[ident]=record;self.payloads[ident]=payload;self.cancel_flags[ident]=threading.Event();self.requests[body['request_id']]=ident
            try:self.queue.put_nowait(ident)
            except queue.Full:
                del self.records[ident],self.payloads[ident],self.cancel_flags[ident],self.requests[body['request_id']]
                raise JobError('QUEUE_FULL','Очередь заполнена; повторите позже',503,True)
            self.persist();return self.public(record),True
    def cancel(self,ident):
        with self.lock:
            r=self.records.get(ident)
            if r is None:raise JobError('NOT_FOUND','Задание не найдено',404)
            if r['state'] in {'succeeded','failed'}:raise JobError('TERMINAL_JOB','Задание уже завершено')
            if r['state'] in {'cancelled','cancelling'}:return self.public(r)
            self.cancel_flags[ident].set();r['state']='cancelled' if r['state']=='queued' else 'cancelling';r['phase']='Отмена';self.persist();return self.public(r)
    def worker(self):
        while not self.stopping.is_set():
            try:ident=self.queue.get(timeout=.2)
            except queue.Empty:continue
            try:
                with self.lock:
                    r=self.records[ident]
                    if r['state']=='cancelled':continue
                    r.update(state='running',phase='Расчёт');self.persist();payload=self.payloads[ident];flag=self.cancel_flags[ident]
                def progress(done,total,result_id):
                    with self.lock:r.update(completed_runs=done,total_runs=total,current_result_id=result_id);self.persist()
                if r['kind']=='run':m,_=execute(payload,self.root,flag.is_set);result_ids=[m['result_id']]
                elif r['kind']=='series':m,_=run_series(payload,self.root,flag.is_set,progress);result_ids=[m['result_id']]
                else:
                    archive=export_result(*payload,cancel=flag.is_set);m={};result_ids=[]
                    with self.lock:r['archive']={'name':payload[1].name,'sha256':archive['sha256'],'bytes':archive['bytes']}
                with self.lock:
                    r.update(state='cancelled' if flag.is_set() else 'succeeded',phase='Отменено' if flag.is_set() else 'Завершено',result_ids=result_ids,current_result_id=result_ids[-1] if result_ids else None)
                    if r['state']=='succeeded':r['completed_runs']=r['total_runs']
                    self.persist()
            except Exception as exc:
                with self.lock:
                    code='EXPORT_FAILED' if r['kind']=='export' else 'SAVE_FAILED' if isinstance(exc,OSError) else 'EXECUTION_FAILED'
                    r.update(state='cancelled' if self.cancel_flags[ident].is_set() else 'failed',phase='Ошибка',error={'code':code,'message':'Операция не завершена; исходные результаты сохранены','field_errors':[],'retryable':True})
                    try:self.persist()
                    except OSError:traceback.print_exc()
                traceback.print_exc()
            finally:self.queue.task_done()
    def close(self):
        with self.lock:
            for ident,r in self.records.items():
                if r['state'] in {'queued','running','cancelling'}:
                    self.cancel_flags[ident].set();r['state']='cancelled';r['phase']='Остановка сервера'
            self.persist()
        self.stopping.set();self.thread.join(timeout=5)
