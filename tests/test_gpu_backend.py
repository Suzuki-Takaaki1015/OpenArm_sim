import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('launcher_gpu_test', Path(__file__).resolve().parents[1] / 'start.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class GPUBackendTests(unittest.TestCase):
    def test_nvidia_candidate_includes_offload(self):
        with patch.object(launcher, 'desktop_options', return_value=([], 'ok')), patch.object(launcher.shutil, 'which', return_value='/usr/bin/nvidia-smi'), patch.object(launcher, 'docker', return_value=subprocess.CompletedProcess([], 0, '{"nvidia": {}}')), patch.object(launcher.Path, 'is_dir', return_value=False):
            options = launcher.gpu_candidates('Linux', 'unix:///var/run/docker.sock')[0][0][1]
            self.assertIn('__NV_PRIME_RENDER_OFFLOAD=1', options)
            self.assertIn('__GLX_VENDOR_LIBRARY_NAME=nvidia', options)

    def test_both_rtx_models_and_intel_misidentification(self):
        args = argparse.Namespace(cpu=False, gpu=False)
        for renderer, mode in [('NVIDIA GeForce RTX 3070', 'gpu'), ('NVIDIA GeForce RTX 3060 Ti', 'gpu'), ('Mesa Intel UHD Graphics 630', 'cpu'), ('llvmpipe', 'cpu')]:
            with self.subTest(renderer=renderer), tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'STATE', Path(directory)), patch.object(launcher, 'gpu_candidates', return_value=([('NVIDIA', ['-e', '__NV_PRIME_RENDER_OFFLOAD=1'])], 'none')), patch.object(launcher, 'docker', return_value=subprocess.CompletedProcess([], 0, 'OpenGL renderer string: ' + renderer)):
                result = launcher.select_backend(args, 'Linux', 'unix://')
                self.assertEqual(result[0], mode)
                if mode == 'gpu':
                    self.assertIn('__NV_PRIME_RENDER_OFFLOAD=1', result[1])

    def test_mesa_fallback(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher, 'STATE', Path(directory)), patch.object(launcher, 'gpu_candidates', return_value=([('NVIDIA', ['nvidia-options']), ('Mesa/DRI', ['mesa-options'])], 'none')), patch.object(launcher, 'docker', side_effect=[subprocess.CompletedProcess([], 1, 'failed'), subprocess.CompletedProcess([], 0, 'OpenGL renderer string: Mesa Intel UHD Graphics 630')]):
            result = launcher.select_backend(argparse.Namespace(cpu=False, gpu=False), 'Linux', 'unix://')
            self.assertEqual(result[0:2], ('gpu', ['mesa-options']))


if __name__ == '__main__':
    unittest.main()
