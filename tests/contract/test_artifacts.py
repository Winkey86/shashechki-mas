import copy,tempfile,unittest
from pathlib import Path
from shashechki.artifacts import execute,verify,replay_inputs,compare,export_result
from shashechki.validation import load,validate
from shashechki.domain import InputError
class ArtifactTests(unittest.TestCase):
    def test_repeat_export_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=load('scenarios/normal.json');a,pa=execute(s,tmp);b,pb=execute(replay_inputs(pa),tmp)
            self.assertNotEqual(a['execution_id'],b['execution_id']);self.assertTrue(compare(pa,pb)['equal'])
            z=Path(tmp)/'demo.zip';export_result(pa,z)
            with self.assertRaises(FileExistsError):export_result(pa,z)
            (pa/'metrics.json').write_text('{}')
            with self.assertRaises(InputError):verify(pa)
    def test_unknown_and_schema(self):
        s=load('scenarios/normal.json');s['surprise']=1
        with self.assertRaises(InputError):validate(s)
        s.pop('surprise');s['schema_version']='99'
        with self.assertRaises(InputError):validate(s)

    def test_incomplete_manifest(self):
        from shashechki.artifacts import read_json,write_json
        with tempfile.TemporaryDirectory() as tmp:
            _,p=execute(load('scenarios/normal.json'),tmp);m=read_json(p/'manifest.json');m['complete']=False;write_json(p/'manifest.json',m)
            with self.assertRaises(InputError) as c:verify(p)
            self.assertEqual(c.exception.code,'RESULT_INCOMPLETE')
