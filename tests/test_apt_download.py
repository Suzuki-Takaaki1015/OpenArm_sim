import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'docker/bootstrap/install_apt.sh'
class AptDownloadTests(unittest.TestCase):
    def run_case(self,mode):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            scripts={
                'timeout':'#!/bin/sh\nshift\nexec "$@"\n',
                'find':'#!/bin/sh\necho switch >> "$APT_TEST_LOG"\n',
                'apt-get':'''#!/bin/sh
printf '%s\\n' "$*" >> "$APT_TEST_LOG"
case "$*" in
*--download-only*)
 if [ "$APT_TEST_MODE" = fail ]; then exit 100; fi
 if [ "$APT_TEST_MODE" = fallback ] && [ ! -e "$APT_TEST_STATE" ]; then touch "$APT_TEST_STATE"; exit 100; fi
 ;;
esac
exit 0
'''}
            for name,body in scripts.items():
                path=root/name;path.write_text(body);path.chmod(0o755)
            env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],'APT_TEST_MODE':mode,'APT_TEST_LOG':str(root/'log'),'APT_TEST_STATE':str(root/'state')}
            result=subprocess.run(['sh',str(SCRIPT),'example-package'],env=env,text=True,capture_output=True)
            return result,(root/'log').read_text()
    def test_primary_success(self):
        result,log=self.run_case('ok');self.assertEqual(result.returncode,0);self.assertNotIn('switch',log);self.assertIn('--no-download',log)
    def test_download_failure_switches_source(self):
        result,log=self.run_case('fallback');self.assertEqual(result.returncode,0);self.assertIn('switch',log);self.assertEqual(log.count('--download-only'),2);self.assertIn('--no-download',log)
    def test_all_fail_never_runs_install(self):
        result,log=self.run_case('fail');self.assertNotEqual(result.returncode,0);self.assertNotIn('--no-download',log)
if __name__=='__main__':unittest.main()
