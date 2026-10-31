import contextlib,io,json,tempfile,unittest
from shashechki.cli import main
class CliTests(unittest.TestCase):
    def call(self,args):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=main(args)
        return code,out.getvalue(),err.getvalue()
    def test_json_codes_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,out,err=self.call(['validate','--scenario','scenarios/normal.json'])
            self.assertEqual(code,0);self.assertTrue(json.loads(out)['valid']);self.assertEqual(err,'')
            code,out,_=self.call(['run','--scenario','scenarios/normal.json','--output-root',tmp]);self.assertEqual(code,0);a=json.loads(out)['path']
            code,out,_=self.call(['run','--replay-inputs',a,'--output-root',tmp]);self.assertEqual(code,0);b=json.loads(out)['path']
            self.assertEqual(self.call(['compare','--left',a,'--right',b])[0],0)
            code,out,err=self.call(['validate','--scenario',tmp+'/missing.json']);self.assertEqual(code,2);self.assertEqual(out,'');self.assertIn('message',json.loads(err))
            self.assertEqual(self.call(['serve','--host','0.0.0.0'])[0],2)
