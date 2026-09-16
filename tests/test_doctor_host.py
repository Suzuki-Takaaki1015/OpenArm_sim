"""Host diagnostics without Docker or ROS; run with unittest discovery."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('oa_doctor', Path(__file__).resolve().parents[1] / 'docker/app/oa_doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

class DoctorHostTests(unittest.TestCase):
    def inspect(self, running=True, version='2', mounts=None):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{'State': {'Running': running}, 'Config': {'Env': ['OPENARM_VERSION='+version]}, 'Mounts': mounts or []}]))

    def invoke(self, effects):
        with patch.object(doctor, 'run', side_effect=effects) as runner, contextlib.redirect_stdout(io.StringIO()) as output:
            code = doctor.host(SimpleNamespace(container='test-container'))
        return code, output.getvalue(), runner

    def test_docker_unavailable(self):
        code, text, _ = self.invoke([FileNotFoundError('docker')])
        self.assertEqual(code, 1); self.assertIn('未確認', text)

    def test_docker_timeout(self):
        code, text, _ = self.invoke([subprocess.TimeoutExpired('docker', 5)])
        self.assertEqual(code, 1); self.assertIn('Docker', text)

    def test_container_absent(self):
        code, text, _ = self.invoke([SimpleNamespace(returncode=1, stderr='No such container')])
        self.assertEqual(code, 1); self.assertIn('未確認', text)

    def test_stopped_does_not_probe(self):
        code, text, runner = self.invoke([self.inspect(running=False)])
        self.assertEqual(code, 1); self.assertIn('停止中', text); self.assertEqual(runner.call_count, 1)

    def test_supported_models(self):
        for version in ('1', '2'):
            with self.subTest(version=version):
                code, text, _ = self.invoke([self.inspect(version=version), SimpleNamespace(returncode=0, stdout='正常\n')])
                self.assertEqual(code, 0); self.assertIn(version+'.0', text)

    def test_invalid_model_is_failure_even_if_probe_passes(self):
        code, text, _ = self.invoke([self.inspect(version='3'), SimpleNamespace(returncode=0, stdout='')])
        self.assertEqual(code, 1); self.assertIn('[要確認] 選択モデル', text)

    def test_saved_model_mismatch_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)/'.openarm'; folder.mkdir()
            (folder/'environment.json').write_text('{"robot_version":"1"}')
            info = self.inspect(mounts=[{'Source':directory, 'Destination':'/workspaces/OpenArm_sim'}])
            code, text, _ = self.invoke([info, SimpleNamespace(returncode=0, stdout='')])
            self.assertEqual(code, 1); self.assertIn('モデル選択の一致', text)

    def test_probe_timeout(self):
        code, text, _ = self.invoke([self.inspect(), subprocess.TimeoutExpired('probe', 17)])
        self.assertEqual(code, 1); self.assertIn('時間切れ', text)

    def test_probe_force_kill_exit(self):
        code, text, _ = self.invoke([self.inspect(), SimpleNamespace(returncode=137, stdout='', stderr='')])
        self.assertEqual(code, 1); self.assertIn('時間切れ', text)

    def test_ros_not_started(self):
        code, text, _ = self.invoke([self.inspect(), SimpleNamespace(returncode=1, stdout='ROSグラフ: 未検出\n')])
        self.assertEqual(code, 1); self.assertIn('未検出', text)

    def test_probe_has_inner_and_outer_deadlines(self):
        _, _, runner = self.invoke([self.inspect(), SimpleNamespace(returncode=0, stdout='')])
        call = runner.call_args
        self.assertIn('--kill-after=1s', call.args[0]); self.assertIn('13s', call.args[0])
        self.assertEqual(call.kwargs['timeout'], 17)

if __name__ == '__main__':
    unittest.main()
