import unittest,tempfile,threading,json,time,http.client
from pathlib import Path
from shashechki.server import LocalServer
class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();root=Path(cls.tmp.name)
        cls.server=LocalServer('127.0.0.1',0,root/'results',root/'jobs.json');cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def request(self,path,body=None,origin=None,raw=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=20);headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        c.request('POST' if body is not None or raw is not None else 'GET',path,body=raw if raw is not None else json.dumps(body) if body is not None else None,headers=headers)
        r=c.getresponse();status=r.status;data=json.loads(r.read());c.close();return status,data
    def wait_job(self,ident):
        until=time.monotonic()+20
        while time.monotonic()<until:
            _,j=self.request('/api/v1/jobs/'+ident)
            if j['state'] in {'succeeded','failed','cancelled'}:return j
            time.sleep(.02)
        self.fail('Job timeout')
    def test_run_and_request_id(self):
        b={'schema_version':'1.0','request_id':'http-normal','kind':'run','scenario_id':'normal','overrides':{}}
        status,j=self.request('/api/v1/jobs',b);self.assertEqual(status,202)
        status,same=self.request('/api/v1/jobs',b);self.assertEqual(status,200);self.assertEqual(same['job_id'],j['job_id'])
        b['scenario_id']='conflict';status,_=self.request('/api/v1/jobs',b);self.assertEqual(status,409)
        done=self.wait_job(j['job_id']);self.assertEqual(done['state'],'succeeded')
        status,data=self.request('/api/v1/results/'+done['result_ids'][0]);self.assertEqual(status,200);self.assertEqual(data['metrics']['completed']['value'],1)
        from shashechki.artifacts import replay_inputs,execute,compare
        saved=self.server.jobs.result_path(done['result_ids'][0]);_,repeated=execute(replay_inputs(saved),self.server.jobs.root)
        self.assertTrue(compare(saved,repeated)['equal'])
        self.assertEqual(self.request('/api/v1/jobs/'+j['job_id']+'/cancel',{})[0],409)
    def test_validation(self):
        for n,extra in enumerate([{'bad':1},{'allocation':{}},{'allocation':None},{'budget':'NaN'}]):
            body={'schema_version':'1.0','request_id':'invalid-'+str(n),'kind':'run','scenario_id':'normal','overrides':extra}
            self.assertEqual(self.request('/api/v1/jobs',body)[0],422)
        self.assertEqual(self.request('/api/v1/jobs',raw='{broken')[0],400)
        self.assertEqual(self.request('/api/v1/jobs',raw='{"kind":"run","kind":"series"}')[0],400)
        self.assertEqual(self.request('/api/v1/jobs',{},origin='https://example.org')[0],403)
        self.assertEqual(self.request('/api/v1/results/../../README.md')[0],404)
    def test_catalog(self):
        status,data=self.request('/api/v1/scenarios');self.assertEqual(status,200);self.assertEqual(len(data['scenarios']),17)
