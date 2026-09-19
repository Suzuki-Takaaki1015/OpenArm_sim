"""Network failure regression checks; no network or Docker required."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pip_download", Path(__file__).resolve().parents[1] / "docker/bootstrap/install_requirements.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PipDownloadTests(unittest.TestCase):
    @patch.object(module.time, "sleep")
    def test_interrupted_body_retried_then_success(self, sleep):
        error = "pip._vendor.urllib3.exceptions.ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org'): Read timed out."
        with patch.object(module, "run_attempt", side_effect=[(2, error), (0, "ok")]) as run:
            self.assertEqual(module.install("requirements.txt"), 0)
        self.assertEqual(run.call_count, 2)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--timeout") + 1], "120")
        self.assertNotIn("--no-cache-dir", command)
        sleep.assert_called_once_with(5)

    @patch.object(module.time, "sleep")
    def test_exhausted_network_failure_stays_failure(self, sleep):
        with patch.object(module, "run_attempt", return_value=(2, "ReadTimeoutError")) as run:
            self.assertEqual(module.install("requirements.txt"), 2)
        self.assertEqual(run.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [5, 10])

    @patch.object(module.time, "sleep")
    def test_dependency_failure_not_retried(self, sleep):
        with patch.object(module, "run_attempt", return_value=(1, "ResolutionImpossible")) as run:
            self.assertEqual(module.install("requirements.txt"), 1)
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()

    def test_real_process_exit_and_output_preserved(self):
        code, output = module.run_attempt([sys.executable, "-c", "import sys; print('ReadTimeoutError', flush=True); sys.exit(2)"])
        self.assertEqual(code, 2)
        self.assertIn("ReadTimeoutError", output)


if __name__ == "__main__":
    unittest.main()
