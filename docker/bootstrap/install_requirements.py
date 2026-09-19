"""Bounded retries for interrupted pip downloads, including older Ubuntu pip."""
import subprocess
import sys
import time

NETWORK_ERRORS = (
    "readtimeouterror", "read timed out", "connecttimeouterror",
    "connection reset", "connection broken", "connection aborted",
    "temporary failure in name resolution", "network is unreachable",
    "newconnectionerror", "incompleteread", "remote end closed connection",
)


def run_attempt(command):
    tail = ""
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace") as process:
        for line in process.stdout:
            print(line, end="", flush=True)
            tail = (tail + line)[-16000:]
        return process.wait(), tail


def install(requirements):
    # --retries alone does not retry a streamed response timeout on older pip.
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--no-input", "--progress-bar", "off", "--timeout", "120",
               "--retries", "3", "-r", requirements]
    for attempt in range(1, 4):
        print(f"[CHECK] Python dependencies: attempt {attempt}/3 (socket timeout 120s)", flush=True)
        code, output = run_attempt(command)
        if code == 0:
            return 0
        if not any(marker in output.lower() for marker in NETWORK_ERRORS):
            return code
        if attempt < 3:
            print("[WARN] Package download interrupted; retrying with cached downloads", flush=True)
            time.sleep(5 * attempt)
    print("[FAIL] Python package download failed after 3 attempts. Check access to "
          "pypi.org and files.pythonhosted.org, then run bash start.sh again. "
          "Completed Docker layers and pip downloads can be reused.", flush=True)
    return code


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: install_requirements.py REQUIREMENTS_FILE")
    raise SystemExit(install(sys.argv[1]))
