import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('recording',Path(__file__).resolve().parents[1]/'docker/app/recording.py')
recording=importlib.util.module_from_spec(spec);spec.loader.exec_module(recording)
class RecordingStorage(unittest.TestCase):
    def test_interrupted_before_manifest_is_visible_and_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'recordings'
            with patch.object(recording,'ROOT',root):
                recording.safe_root()
                session=root/'partial';session.mkdir();(session/'config').mkdir()
                (session/'config/sentinel').write_text('preserved')
                self.assertIn('partial',recording.previous_status())
                self.assertEqual((session/'config/sentinel').read_text(),'preserved')
                recording.atomic_json(session/'openarm.json',{'state':'complete'})
                self.assertNotIn('partial',recording.previous_status())
    def test_links_and_traversal_never_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary);target=parent/'target';target.mkdir();(target/'sentinel').write_text('keep')
            root=parent/'recordings';root.symlink_to(target,target_is_directory=True)
            with patch.object(recording,'ROOT',root):
                with self.assertRaises(ValueError):recording.safe_root()
            self.assertEqual((target/'sentinel').read_text(),'keep')
            for value in ('../escape','/tmp/data','a/b','a\\b','', 'x'*65):
                with self.assertRaises(ValueError):recording.valid_name(value)
if __name__=='__main__':unittest.main()
