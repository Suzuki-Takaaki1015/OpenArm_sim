import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('setup_vscode', Path(__file__).resolve().parents[1] / 'scripts/setup_vscode.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VSCodeBootstrapTests(unittest.TestCase):
    def test_existing_offline_does_not_install(self):
        with patch.dict(os.environ, {'OPENARM_OFFLINE': '1'}), patch.object(MODULE.shutil, 'which', return_value='/usr/bin/code'), patch.object(MODULE, 'run', return_value=MODULE.EXTENSION) as run, patch.object(MODULE.urllib.request, 'urlopen') as download:
            MODULE.setup()
            run.assert_called_once_with(['/usr/bin/code', '--list-extensions'], timeout=120)
            download.assert_not_called()

    def test_missing_code_offline_stops_without_network(self):
        with patch.dict(os.environ, {'OPENARM_OFFLINE': '1'}), patch.object(MODULE.shutil, 'which', return_value=None), patch.object(MODULE.urllib.request, 'urlopen') as download, patch.object(MODULE.subprocess, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'host VS Code is missing'):
                MODULE.setup()
            download.assert_not_called()
            command.assert_not_called()

    def test_missing_extension_offline_stops(self):
        with patch.dict(os.environ, {'OPENARM_OFFLINE': '1'}), patch.object(MODULE.shutil, 'which', return_value='/usr/bin/code'), patch.object(MODULE, 'run', return_value='') as run:
            with self.assertRaisesRegex(RuntimeError, 'extension is missing'):
                MODULE.setup()
            self.assertEqual(run.call_count, 1)

    def test_missing_code_installs_then_checks_extension(self):
        with patch.dict(os.environ, {'OPENARM_OFFLINE': '0'}), patch.object(MODULE.shutil, 'which', side_effect=[None, '/usr/bin/code']), patch.object(MODULE.urllib.request, 'urlopen', return_value=io.BytesIO(b'fake-deb')), patch.object(MODULE, 'run', side_effect=['code', 'amd64', '', '', MODULE.EXTENSION]) as run, patch.object(MODULE.subprocess, 'run') as command:
            MODULE.setup()
            self.assertEqual(command.call_count, 2)
            self.assertIn('update', command.call_args_list[0].args[0])
            self.assertIn('install', command.call_args_list[1].args[0])
            self.assertEqual(run.call_args_list[3].args[0], ['/usr/bin/code', '--install-extension', MODULE.EXTENSION])

    def test_wrong_package_never_installed(self):
        with patch.dict(os.environ, {'OPENARM_OFFLINE': '0'}), patch.object(MODULE.shutil, 'which', return_value=None), patch.object(MODULE.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad-deb')), patch.object(MODULE, 'run', return_value='other-package'), patch.object(MODULE.subprocess, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'not VS Code'):
                MODULE.setup()
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
