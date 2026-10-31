import tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from shashechki.artifacts import execute,export_result,verify,reserve
from shashechki.validation import load
from shashechki.domain import InputError
class ExportTests(unittest.TestCase):
    def test_incomplete_collision_and_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,p=execute(load('scenarios/normal.json'),tmp);z=Path(tmp)/'demo.zip'
            with patch('shashechki.artifacts.zipfile.ZipFile',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):export_result(p,z)
            self.assertFalse(z.exists());verify(p)
            export_result(p,z)
            with zipfile.ZipFile(z) as archive:self.assertIn('trace.jsonl',archive.namelist())
            with self.assertRaises(FileExistsError):export_result(p,z)
            from types import SimpleNamespace
            (Path(tmp)/('run-'+'a'*20)).mkdir()
            with patch('shashechki.artifacts.uuid.uuid4',return_value=SimpleNamespace(hex='a'*32)):
                with self.assertRaises(OSError):reserve(tmp)
            (p/'metrics.json').unlink()
            with self.assertRaises(InputError):verify(p)
