"""Локальная HTTP-оболочка, без исполнения модели в обработчике запроса."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,unquote
import json,mimetypes,re,sys
from .domain import InputError,ID_PATTERN
from .artifacts import canonical,read_json,result_data,safe_file
from .jobs import Jobs,JobError

ROOT=Path(__file__).resolve().parents[2]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):print(fmt%args,file=sys.stderr)
    def json(self,status,value,headers=None):
        data=canonical(value);self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def error(self,status,code,message,request_id=None,field_errors=None,retryable=False):
        self.json(status,{'error':{'code':code,'message':message,'field_errors':field_errors or [],'retryable':retryable},'request_id':request_id},{'Retry-After':'1'} if status==503 else None)
    def file(self,path):
        path=Path(path)
        if not path.is_file():return self.error(404,'NOT_FOUND','Файл не найден')
        mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream';self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff')
        if path.suffix in {'.zip','.csv'}:self.send_header('Content-Disposition','attachment; filename="'+path.name+'"')
        self.end_headers()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):self.wfile.write(block)
    def do_GET(self):
        path=unquote(urlsplit(self.path).path);jobs=self.server.jobs
        try:
            export_match=re.fullmatch(r'/api/v1/exports/([a-zA-Z0-9_-]+\.zip)',path)
            if export_match:return self.file(jobs.root/'exports'/export_match[1])
            if path=='/api/v1/scenarios':return self.json(200,{'scenarios':jobs.scenarios_catalog()})
            if path=='/api/v1/results':
                rows=[]
                for directory in sorted(jobs.root.iterdir(),key=lambda p:p.stat().st_mtime_ns,reverse=True):
                    if not directory.is_dir() or not directory.name.startswith(('run-','series-')):continue
                    try:
                        m=read_json(directory/'manifest.json');rows.append({k:m.get(k) for k in ('result_id','kind','title','complete','termination_reason','scenario_id','experiment_id','completed_runs','total_runs','complete_pairs')})
                    except (OSError,ValueError):rows.append({'result_id':directory.name,'complete':False,'kind':'incomplete','title':'Неполный результат'})
                return self.json(200,{'results':rows})
            if path=='/api/v1/materials':
                rows=[]
                for i in range(1,5):
                    p=ROOT/'reports'/f'lab-{i:02}.pdf'
                    if p.exists():rows.append({'title':f'Лабораторная работа №{i}','url':f'/reports/lab-{i:02}.pdf','kind':'report','bytes':p.stat().st_size})
                for name,title in [('source.zip','Исходный код'),('demo.zip','Демонстрационные материалы')]:
                    p=ROOT/'evidence'/name
                    if p.exists():rows.append({'title':title,'url':'/materials/'+name,'kind':'appendix','bytes':p.stat().st_size})
                return self.json(200,{'materials':rows})
            m=re.fullmatch(r'/api/v1/jobs/([\w-]+)',path)
            if m:return self.json(200,jobs.get(m[1]))
            m=re.fullmatch(r'/api/v1/results/([\w-]+)(?:/artifacts/(.+))?',path)
            if m:
                directory=jobs.result_path(m[1]);manifest=read_json(directory/'manifest.json')
                if m[2]:
                    if m[2] not in manifest['files']:raise JobError('NOT_FOUND','Артефакт не найден',404)
                    return self.file(safe_file(directory,m[2]))
                return self.json(200,result_data(directory))
            if path.startswith('/fonts/'):
                name=path.removeprefix('/fonts/')
                if name not in {'ibm-plex-sans-regular.ttf','ibm-plex-sans-medium.ttf','ibm-plex-sans-semibold.ttf','OFL.txt'}:raise JobError('NOT_FOUND','Шрифт не найден',404)
                return self.file(ROOT/'design'/'fonts'/name)
            if re.fullmatch(r'/reports/lab-0[1-4]\.pdf',path):return self.file(ROOT/path.lstrip('/'))
            if path in {'/materials/source.zip','/materials/demo.zip'}:return self.file(ROOT/'evidence'/path.split('/')[-1])
            name='index.html' if path=='/' else path.lstrip('/')
            if name not in {'index.html','styles.css','app.js','api.js','playback.js','map.js','panels.js'}:raise JobError('NOT_FOUND','Страница не найдена',404)
            return self.file(ROOT/'web'/name)
        except JobError as exc:self.error(exc.status,exc.code,exc.message,retryable=exc.retryable)
        except InputError as exc:self.error(409 if exc.code=='RESULT_INCOMPLETE' else 422,exc.code,str(exc),field_errors=[exc.detail()])
        except (OSError,ValueError):self.error(500,'READ_FAILED','Не удалось прочитать результат')
    def do_POST(self):
        request_id=None
        try:
            port=self.server.server_port;hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
            if self.headers.get('Host') not in hosts or (self.headers.get('Origin') and self.headers['Origin'] not in {'http://'+h for h in hosts}):return self.error(403,'INVALID_ORIGIN','Недопустимый источник запроса')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.error(415,'UNSUPPORTED_MEDIA_TYPE','Требуется application/json')
            try:length=int(self.headers.get('Content-Length','-1'))
            except ValueError:return self.error(400,'INVALID_JSON','Неверный размер тела')
            if length<0:return self.error(400,'INVALID_JSON','Отсутствует размер тела')
            if length>2*1024*1024:return self.error(413,'BODY_TOO_LARGE','Слишком большое тело запроса')
            def unique(pairs):
                result={}
                for k,v in pairs:
                    if k in result:raise ValueError('Повтор поля')
                    result[k]=v
                return result
            try:body=json.loads(self.rfile.read(length),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Нечисловое значение')))
            except (ValueError,UnicodeError):return self.error(400,'INVALID_JSON','Повреждённый JSON')
            if not isinstance(body,dict):raise InputError('Ожидается JSON-объект')
            request_id=body.get('request_id');path=unquote(urlsplit(self.path).path)
            if path=='/api/v1/jobs':
                job,created=self.server.jobs.submit(body);return self.json(202 if created else 200,job)
            m=re.fullmatch(r'/api/v1/jobs/([\w-]+)/cancel',path)
            if m:
                if body:raise InputError('Для отмены требуется пустой объект')
                return self.json(200,self.server.jobs.cancel(m[1]))
            raise JobError('NOT_FOUND','Команда не найдена',404)
        except JobError as exc:self.error(exc.status,exc.code,exc.message,request_id,retryable=exc.retryable)
        except InputError as exc:self.error(409 if exc.code=='RESULT_INCOMPLETE' else 422,exc.code,str(exc),request_id,[exc.detail()])
        except OSError:self.error(500,'SAVE_FAILED','Не удалось сохранить задание',request_id)

class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,host,port,output_root,registry=None):
        if host!='127.0.0.1':raise InputError('Сервер поддерживает только 127.0.0.1')
        super().__init__((host,port),Handler)
        self.jobs=Jobs(output_root,ROOT/'scenarios',registry or ROOT/'.local'/'jobs.json')
    def server_close(self):
        if hasattr(self,'jobs'):self.jobs.close()
        super().server_close()
