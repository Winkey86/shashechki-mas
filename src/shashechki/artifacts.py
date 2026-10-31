"""Неизменяемые каталоги и завершающий манифест с контрольными суммами."""
from pathlib import Path,PurePosixPath
from copy import deepcopy
from datetime import datetime,timezone
from time import perf_counter
import hashlib,json,csv,os,uuid,sys,zipfile
from .domain import MODEL_VERSION,SCHEMA_VERSION,InputError
from .metrics import json_default

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False,default=json_default).encode('utf-8')
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def write_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('xb') as f:f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def read_json(path):
    with Path(path).open(encoding='utf-8') as f:return json.load(f)
def reserve(root,prefix='run'):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    for _ in range(10):
        identity=prefix+'-'+uuid.uuid4().hex[:20];path=root/identity
        try:path.mkdir();return identity,path
        except FileExistsError:continue
    raise OSError('Не удалось зарезервировать каталог результата')
def file_manifest(path):
    return {str(p.relative_to(path)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(path.rglob('*')) if p.is_file() and p!=path/'manifest.json' and not p.name.endswith('.tmp')}
def write_csv(path,rows):
    if not rows:Path(path).write_text('',encoding='utf-8');return
    with Path(path).open('x',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
def save_run(run,root,wall_time_ms=0):
    ident,path=reserve(root);started=perf_counter();inputs=deepcopy(run.inputs);inputs.pop('config',None)
    input_hash=digest(inputs);case_id=digest({'model_version':MODEL_VERSION,'schema_version':SCHEMA_VERSION,'input_hash':input_hash,'config':run.config})
    write_json(path/'input.json',inputs);write_json(path/'config.json',run.config)
    with (path/'trace.jsonl').open('xb') as f:
        for event in run.trace:f.write(canonical(event)+b'\n')
    for name,value in [('metrics.json',run.metrics),('orders.json',run.orders),('drivers.json',run.drivers),('faults.json',run.fault_results),('playback.json',run.playback)]:write_json(path/name,value)
    write_csv(path/'orders.csv',run.orders);write_csv(path/'drivers.csv',run.drivers)
    canonical_hash=digest({'trace':run.trace,'metrics':run.metrics,'orders':run.orders,'drivers':run.drivers,'faults':run.fault_results})
    manifest={'schema_version':SCHEMA_VERSION,'model_version':MODEL_VERSION,'kind':'run','result_id':ident,'execution_id':ident,'case_id':case_id,'input_hash':input_hash,'scenario_id':run.inputs['scenario_id'],'title':run.inputs.get('title',run.inputs['scenario_id']),
        'complete':run.termination_reason!='cancelled','termination_reason':run.termination_reason,'canonical_sha256':canonical_hash,'files':file_manifest(path),'technical':{'python_version':sys.version.split()[0],'created_at_utc':datetime.now(timezone.utc).isoformat(),'calculation_ms':wall_time_ms,'save_ms':(perf_counter()-started)*1000}}
    write_json(path/'manifest.json',manifest);return manifest,path

def safe_file(root,name):
    rel=PurePosixPath(name)
    if rel.is_absolute() or not rel.parts or any(p in {'..','.'} for p in rel.parts) or '\\' in name:raise InputError('Недопустимый путь артефакта')
    path=Path(root)/name
    if not path.resolve().is_relative_to(Path(root).resolve()):raise InputError('Путь за пределами результата')
    return path

def verify(path,require_complete=True):
    path=Path(path);m=read_json(path/'manifest.json')
    if m.get('schema_version')!=SCHEMA_VERSION:raise InputError('Неподдерживаемая версия результата',code='UNSUPPORTED_SCHEMA')
    if require_complete and not m.get('complete'):raise InputError('Результат не завершён',code='RESULT_INCOMPLETE')
    for name,info in m['files'].items():
        p=safe_file(path,name)
        if not p.is_file() or p.stat().st_size!=info['bytes'] or sha(p)!=info['sha256']:raise InputError('Повреждён артефакт: '+name,code='HASH_MISMATCH')
    return m

def execute(inputs,root,cancel=None):
    from .protocol import simulate
    start=perf_counter();run=simulate(inputs,cancel);return save_run(run,root,(perf_counter()-start)*1000)

def replay_inputs(path):
    verify(path);data=read_json(Path(path)/'input.json');data['config']=read_json(Path(path)/'config.json');return data

def compare(left,right):
    a,b=verify(left),verify(right)
    return {'equal':a['case_id']==b['case_id'] and a['canonical_sha256']==b['canonical_sha256'],'left':a['canonical_sha256'],'right':b['canonical_sha256'],'technical_excluded':['execution_id','calendar timestamps','paths','wall-clock timing']}

def export_result(source,destination,cancel=None):
    source=Path(source);m=verify(source);destination=Path(destination)
    fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);tmp=destination.with_name(destination.name+'.tmp')
    try:
        with zipfile.ZipFile(tmp,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted([*m['files'],'manifest.json']):
                if cancel and cancel():raise InterruptedError('Экспорт отменён')
                archive.write(safe_file(source,name),arcname=name)
        os.replace(tmp,destination)
    except BaseException:
        destination.unlink(missing_ok=True);tmp.unlink(missing_ok=True);raise
    return {'path':str(destination),'sha256':sha(destination),'bytes':destination.stat().st_size}

def result_data(path,check=False):
    m=verify(path) if check else read_json(Path(path)/'manifest.json')
    if not m.get('complete'):raise InputError('Неполный результат',code='RESULT_INCOMPLETE')
    result={'manifest':m,'metrics':read_json(Path(path)/('metrics.json' if m['kind']=='run' else 'summary.json'))}
    if m['kind']=='run':
        result['orders']=read_json(Path(path)/'orders.json');result['drivers']=read_json(Path(path)/'drivers.json');result['faults']=read_json(Path(path)/'faults.json')
    return result
