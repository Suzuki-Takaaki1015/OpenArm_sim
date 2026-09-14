import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import start

class DisplayTests(unittest.TestCase):
    def args(self, **kw):
        return argparse.Namespace(display=kw.get('display','auto'), cpu=True, gpu=False)
    def test_desktop_cpu_is_native(self):
        with tempfile.TemporaryDirectory() as d, patch.object(start,'STATE',Path(d)), patch.object(start,'desktop_options',return_value=(['-e','LIBGL_ALWAYS_SOFTWARE=0'],'desktop')), patch.object(start,'docker',return_value=subprocess.CompletedProcess([],0,'OpenGL renderer string: llvmpipe')):
            mode,opts,_=start.select_presentation(self.args(),'Linux','unix://docker')
            self.assertEqual(mode,'native-cpu')
            self.assertIn('LIBGL_ALWAYS_SOFTWARE=1',opts)
    def test_headless_is_browser(self):
        with patch.object(start,'desktop_options',return_value=(None,'headless')):
            self.assertEqual(start.select_presentation(self.args(),'Linux','unix://docker')[0],'cpu')
    def test_native_failure_falls_back(self):
        with tempfile.TemporaryDirectory() as d, patch.object(start,'STATE',Path(d)), patch.object(start,'desktop_options',return_value=([],'desktop')), patch.object(start,'docker',return_value=subprocess.CompletedProcess([],1,'cannot open display')):
            self.assertEqual(start.select_presentation(self.args(),'Linux','unix://docker')[0],'cpu')
            with self.assertRaises(RuntimeError):start.select_presentation(self.args(display='native'),'Linux','unix://docker')
    def test_browser_override_skips_native(self):
        with patch.object(start,'desktop_options',side_effect=AssertionError('must not probe')):
            self.assertEqual(start.select_presentation(self.args(display='browser'),'Linux','unix://docker')[0],'cpu')

if __name__=='__main__':unittest.main()
