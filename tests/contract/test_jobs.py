import unittest,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
from shashechki.jobs import Jobs,JobError
from shashechki.artifacts import write_json
class JobsTests(unittest.TestCase):
    def test_queue_cancel_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);started=threading.Event();release=threading.Event()
            def blocked(inputs,output,cancel):
                started.set();release.wait(5);return ({'result_id':'test'},output)
            with patch('shashechki.jobs.execute',blocked):
                jobs=Jobs(root/'results','scenarios',root/'jobs.json')
                def submit(n):return jobs.submit({'schema_version':'1.0','request_id':'q-'+str(n),'kind':'run','scenario_id':'normal'})[0]
                a=submit(0);self.assertTrue(started.wait(2));b=submit(1);c=submit(2)
                with self.assertRaises(JobError) as caught:submit(3)
                self.assertEqual(caught.exception.status,503)
                self.assertEqual(jobs.cancel(b['job_id'])['state'],'cancelled')
                self.assertEqual(jobs.cancel(a['job_id'])['state'],'cancelling')
                release.set();jobs.queue.join();self.assertEqual(jobs.get(a['job_id'])['state'],'cancelled');jobs.close()
            write_json(root/'jobs.json',{'old':{'job_id':'old','request_id':'old','kind':'run','state':'running','body_hash':'x'}})
            jobs=Jobs(root/'results','scenarios',root/'jobs.json');self.assertEqual(jobs.get('old')['error']['code'],'INTERRUPTED');jobs.close()
    def test_storage_failure_does_not_kill_worker(self):
        import contextlib,io
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jobs=Jobs(root/'results','scenarios',root/'jobs.json')
            body={'schema_version':'1.0','request_id':'io-failure','kind':'run','scenario_id':'normal'}
            with contextlib.redirect_stderr(io.StringIO()),patch.object(jobs,'persist',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):jobs.submit(body)
                jobs.queue.join()
            failed,_=jobs.submit(body);self.assertEqual(failed['state'],'failed');self.assertEqual(failed['error']['code'],'SAVE_FAILED');self.assertTrue(jobs.thread.is_alive())
            body['request_id']='after-io';next_job,_=jobs.submit(body);jobs.queue.join();self.assertEqual(jobs.get(next_job['job_id'])['state'],'succeeded');jobs.close()
