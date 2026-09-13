import unittest
from unittest.mock import patch
import start

class LauncherTest(unittest.TestCase):
    def test_software_is_not_gpu(self):
        for renderer in ('llvmpipe (LLVM 18)', 'softpipe', 'Software Rasterizer'):
            self.assertFalse(start.hardware_renderer('OpenGL renderer string: '+renderer))
        self.assertFalse(start.hardware_renderer('NVIDIA device found, but no GL context'))
        self.assertTrue(start.hardware_renderer('OpenGL renderer string: NVIDIA RTX 4090'))

    def test_nonlinux_uses_cpu_backend(self):
        candidates, reason=start.gpu_candidates('Windows','npipe://docker_engine')
        self.assertEqual(candidates,[])
        self.assertTrue(reason)

    def test_ssh_without_display_is_cpu(self):
        with patch.dict(start.os.environ, {'DISPLAY':''}):
            self.assertEqual(start.gpu_candidates('Linux','unix:///var/run/docker.sock')[0],[])

    def test_other_checkout_container_is_protected(self):
        import subprocess,json
        response=subprocess.CompletedProcess([],0,json.dumps([{'Config':{'Labels':{start.LABEL:'/another/checkout'}}}]))
        with patch.object(start,'docker',return_value=response):
            with self.assertRaises(RuntimeError):start.existing()

    def test_forced_gpu_does_not_silently_fallback(self):
        import argparse
        with patch.object(start,'gpu_candidates',return_value=([],'No GPU')):
            with self.assertRaises(RuntimeError):
                start.select_backend(argparse.Namespace(cpu=False,gpu=True),'Linux','unix://docker')

if __name__=='__main__':unittest.main()
